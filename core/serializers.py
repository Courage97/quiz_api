from rest_framework import serializers
from .models import (
    User, Quiz, Question, LiveSession,
    Participant, LiveQuestion, ParticipantAnswer, Feedback
)

# ─── User Serializer (Optional if needed) ─────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_host']


# ─── Question Serializer ──────────────────────────────────────

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'text', 'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'is_true_false'
        ]
        read_only_fields = ['correct_option']  # hide for participant response


# ─── Quiz Serializer ───────────────────────────────────────────

class QuizSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ['id', 'title', 'created_by', 'created_at']
        read_only_fields = ['created_by', 'created_at']

# ____ Questions serializers __________________________________

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            'id', 'quiz', 'text',
            'option_a', 'option_b', 'option_c', 'option_d',
            'correct_option', 'is_true_false'
        ]


# ─── Live Session Serializer ──────────────────────────────────

class LiveSessionSerializer(serializers.ModelSerializer):
    quiz = QuizSerializer(read_only=True)
    quiz_id = serializers.PrimaryKeyRelatedField(
        queryset=Quiz.objects.all(), source='quiz', write_only=True
    )
    host = UserSerializer(read_only=True)  # ✅ Make host read-only

    class Meta:
        model = LiveSession
        fields = ['session_code', 'quiz', 'quiz_id', 'host', 'is_active', 'started_at']
        read_only_fields = ['session_code', 'host', 'started_at']


# ─── Participant Serializer ───────────────────────────────────

class ParticipantSerializer(serializers.ModelSerializer):
    session = serializers.SlugRelatedField(slug_field='session_code', queryset=LiveSession.objects.all())

    class Meta:
        model = Participant
        fields = ['id', 'name', 'session', 'score', 'joined_at']
        read_only_fields = ['score', 'joined_at']


# ─── Live Question Serializer ─────────────────────────────────

class LiveQuestionSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    question_id = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all(), source='question', write_only=True)
    session = serializers.SlugRelatedField(slug_field='session_code', queryset=LiveSession.objects.all())

    class Meta:
        model = LiveQuestion
        fields = ['id', 'session', 'question', 'question_id', 'displayed_at', 'duration_seconds']


# ─── Participant Answer Serializer ────────────────────────────

class ParticipantAnswerSerializer(serializers.ModelSerializer):
    participant = serializers.PrimaryKeyRelatedField(queryset=Participant.objects.all())
    question = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all())

    class Meta:
        model = ParticipantAnswer
        fields = ['id', 'participant', 'question', 'selected_option', 'is_correct', 'answered_at']
        read_only_fields = ['is_correct', 'answered_at']

    def create(self, validated_data):
        # Calculate is_correct based on the question's correct answer
        question = validated_data['question']
        selected_option = validated_data['selected_option']
        is_correct = question.correct_option.upper() == selected_option.upper()
        
        validated_data['is_correct'] = is_correct
        return super().create(validated_data)

# ─── Feedback Serializer ──────────────────────────────────────

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = '__all__'
        read_only_fields = ['submitted_at']
