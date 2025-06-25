from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.utils.crypto import get_random_string
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from .serializers import QuestionSerializer
import threading
import logging
from rest_framework.exceptions import ValidationError
from django.db.models import Count, F, Q
from .models import User
from .models import Quiz
from .serializers import QuizSerializer
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password
from .models import (
    Quiz, LiveSession, Participant, LiveQuestion,
    Question, ParticipantAnswer, Feedback
)
from .serializers import (
    LiveSessionSerializer, ParticipantSerializer,
    LiveQuestionSerializer, ParticipantAnswerSerializer,
    FeedbackSerializer
)

@api_view(['POST'])
def register_host(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')

    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already exists."}, status=400)

    user = User.objects.create(
        username=username,
        email=email,
        password=make_password(password),
        is_host=True,  # 👈 mark as host
    )
    return Response({"message": "Host registered successfully."}, status=201)

# ________Host: Create and get quiz____________________________

class QuizListCreateView(generics.ListCreateAPIView):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class QuizDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]

# _____Host: Question views___________________________________

class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        quiz_id = self.request.query_params.get('quiz')
        if quiz_id:
            return Question.objects.filter(quiz_id=quiz_id)
        return Question.objects.all()

class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]

# ─── Host: Create a Live Session ─────────────────────────────

class LiveSessionCreateView(generics.CreateAPIView):
    queryset = LiveSession.objects.all()
    serializer_class = LiveSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        code = get_random_string(6).upper()
        serializer.save(host=self.request.user, session_code=code)


# ─── Guest: Join a Session by Code ───────────────────────────

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def join_session(request):
    session_code = request.data.get('session_code')
    name = request.data.get('name')

    session = get_object_or_404(LiveSession, session_code=session_code, is_active=True)
    participant = Participant.objects.create(session=session, name=name)

    serializer = ParticipantSerializer(participant)
    return Response(serializer.data, status=201)


# ─── Host: Push Question Live ───────────────────────────────

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def push_question(request, code):
    try:
        session = LiveSession.objects.get(session_code=code, host=request.user)
    except LiveSession.DoesNotExist:
        return Response({"error": "Session not found or unauthorized."}, status=404)

    question_id = request.data.get('question_id')
    if not question_id:
        return Response({"error": "Missing question_id."}, status=400)

    try:
        question = Question.objects.get(id=question_id, quiz=session.quiz)
    except Question.DoesNotExist:
        return Response({"error": "Question not found in quiz."}, status=404)

    # Create the LiveQuestion
    live_q = LiveQuestion.objects.create(session=session, question=question, duration_seconds=60)
    serializer = LiveQuestionSerializer(live_q)

    # Build leaderboard
    participants = session.participants.order_by('-score')
    leaderboard = [
        {'name': p.name, 'score': p.score}
        for p in participants
    ]

    # Broadcast question + leaderboard
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'session_{code}',
        {
            'type': 'send_question_with_leaderboard',
            'question': serializer.data,
            'start_time': live_q.displayed_at.isoformat(),
            'duration': live_q.duration_seconds,
            'leaderboard': leaderboard
        }
    )

    # Start timer
    start_question_timer(live_q)

    return Response(serializer.data, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def quiz_questions_view(request, pk):
    questions = Question.objects.filter(quiz_id=pk)
    serializer = QuestionSerializer(questions, many=True)
    return Response(serializer.data)


# ─── Participant: Submit Answer ──────────────────────────────
logger = logging.getLogger(__name__)

class ParticipantAnswerCreateView(generics.CreateAPIView):
    queryset = ParticipantAnswer.objects.all()
    serializer_class = ParticipantAnswerSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        logger.info(f"📨 Received answer submission: {request.data}")
        logger.info(f"🔐 Authenticated user: {request.user if request.user.is_authenticated else 'Anonymous'}")

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"❌ Serializer validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            answer = self.perform_create(serializer)
            output_serializer = self.get_serializer(answer)
            headers = self.get_success_headers(output_serializer.data)
            return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        except ValidationError as e:
            logger.error(f"⚠️ Validation error in perform_create: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.exception("🔥 Unexpected error in perform_create")
            return Response(
                {"detail": "An unexpected error occurred while processing your answer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def perform_create(self, serializer):
        question = serializer.validated_data['question']
        participant = serializer.validated_data['participant']

        logger.info(f"🛠 Processing answer from participant {participant.id} for question {question.id}")

        session = participant.session
        logger.info(f"🧾 Session {session.session_code} is_active: {session.is_active}")

        if not session.is_active:
            logger.warning(f"⚠️ Session {session.session_code} is not active")
            raise ValidationError("This quiz session has ended. No more answers allowed.")

        live_q = LiveQuestion.objects.filter(
            question=question,
            session=session
        ).order_by('-displayed_at').first()

        if not live_q:
            logger.warning(f"⚠️ No active LiveQuestion found for question {question.id} in session {session.session_code}")
            raise ValidationError("This question is not currently active.")

        logger.info(f"📍 Found LiveQuestion {live_q.id}, displayed_at: {live_q.displayed_at}")

        if not live_q.is_active():
            logger.warning(f"⏰ LiveQuestion {live_q.id} has expired")
            raise ValidationError("Time's up! You can no longer answer this question.")

        existing_answer = ParticipantAnswer.objects.filter(
            participant=participant,
            question=question
        ).first()

        if existing_answer:
            logger.warning(f"🔁 Duplicate answer by participant {participant.id} for question {question.id}")
            raise ValidationError("You have already answered this question.")

        logger.info("💾 Saving answer...")
        answer = serializer.save()

        answer.is_correct = (answer.selected_option.upper() == question.correct_option.upper())
        answer.save()

        logger.info(f"✅ Answer saved. Correct: {answer.is_correct}")

        if answer.is_correct:
            participant.score += 10
            participant.save()
            logger.info(f"🏆 Participant {participant.id} score updated to {participant.score}")

        return answer    
    
# ─── Host: View Session Results / Leaderboard ────────────────

@api_view(['GET'])
def session_results(request, code):
    participant_id = request.GET.get('participant')

    session = get_object_or_404(LiveSession, session_code=code)
    participants = Participant.objects.filter(session=session)

    leaderboard = participants.annotate(
        correct_count=Count(
            'participantanswer',
            filter=Q(participantanswer__selected_option=F('participantanswer__question__correct_option'))
        )
    ).values('id', 'name', 'correct_count').order_by('-correct_count')

    participant_data = None
    if participant_id:
        try:
            participant = participants.get(id=participant_id)
            participant_data = {
                "id": participant.id,
                "name": participant.name,
                "score": participant.score,
            }
        except Participant.DoesNotExist:
            pass

    return Response({
        "participant": participant_data,
        "leaderboard": leaderboard
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def end_session(request, code):
    session = get_object_or_404(LiveSession, session_code=code, host=request.user)

    session.end()

    # Broadcast end event
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'session_{code}',
        {
            'type': 'session_ended',
            'message': f"Session {code} has ended."
        }
    )

    return Response({"detail": "Session ended successfully."})


# ─── Feedback Submission ─────────────────────────────────────

@api_view(['POST'])
def feedback_create(request):
    serializer = FeedbackSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({'message': 'Thanks for your feedback!'}, status=201)
    return Response(serializer.errors, status=400)


def get_unanswered_players(session_code, question_id):
    session = LiveSession.objects.get(session_code=session_code)
    question = Question.objects.get(id=question_id)

    participants = session.participants.all()
    answered_ids = ParticipantAnswer.objects.filter(
        question=question,
        participant__in=participants
    ).values_list('participant_id', flat=True)

    unanswered = participants.exclude(id__in=answered_ids)

    return [p.name for p in unanswered]

def start_question_timer(live_q):
    def end_timer():
        correct_option = live_q.question.correct_option
        session = live_q.session
        session_code = session.session_code

        # Get all correct answers
        correct_answers = ParticipantAnswer.objects.filter(
            question=live_q.question,
            participant__session=session,
            is_correct=True
        ).select_related('participant')

        correct_participants = [a.participant.name for a in correct_answers]
        total = ParticipantAnswer.objects.filter(
            question=live_q.question,
            participant__session=session
        ).count()

        # Broadcast correct answer + who got it right
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'session_{session_code}',
            {
                'type': 'reveal_answer',
                'question_id': live_q.question.id,
                'correct_option': correct_option,
                'correct_participants': correct_participants,
                'total_answers': total,
                'correct_count': len(correct_participants)
            }
        )

    threading.Timer(live_q.duration_seconds, end_timer).start()


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def participant_summary(request, code):
    participant_id = request.query_params.get('participant_id')
    session = get_object_or_404(LiveSession, session_code=code)
    participant = get_object_or_404(Participant, id=participant_id, session=session)

    total_questions = session.quiz.questions.count()
    total_answers = ParticipantAnswer.objects.filter(participant=participant).count()
    correct_answers = ParticipantAnswer.objects.filter(participant=participant, is_correct=True).count()

    return Response({
        'participant': participant.name,
        'score': participant.score,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'total_answers': total_answers,
        'accuracy': round((correct_answers / total_questions) * 100 if total_questions > 0 else 0, 1)
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def session_summary(request, code):
    try:
        session = LiveSession.objects.get(session_code=code, host=request.user)
    except LiveSession.DoesNotExist:
        return Response({'error': 'Session not found or unauthorized'}, status=404)

    participants = Participant.objects.filter(session=session).annotate(
        correct_count=Count(
            'participantanswer',
            filter=Q(participantanswer__selected_option=F('participantanswer__question__correct_option'))
        )
    ).values('name', 'score', 'correct_count')  # include score if needed

    feedback = Feedback.objects.filter(participant__session=session).values(
      'id', 'rating', 'participant__name', 'comments'
    )

    return Response({
        'session_code': session.session_code,
        'quiz_title': session.quiz.title,
        'participants': list(participants),
        'feedback': list(feedback)
    })


