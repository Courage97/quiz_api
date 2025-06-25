import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import LiveSession, LiveQuestion, Question, ParticipantAnswer, Participant
import asyncio
from django.db import models


class LiveSessionConsumer(AsyncWebsocketConsumer):
    last_revealed_question_id = None
    async def connect(self):
        print("🔌 WebSocket hit:", self.scope["path"])
        self.session_code = self.scope['url_route']['kwargs']['code']
        self.group_name = f'session_{self.session_code}'

        try:
            session_exists = await database_sync_to_async(
            LiveSession.objects.filter(session_code=self.session_code).exists
        )()


            if not session_exists:
                await self.close(code=4404)  # Custom close code for "not found"
                return

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close(code=4500)  # Custom close code for server error

    async def disconnect(self, close_code):
        # Remove from group when disconnecting
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_leaderboard(self, event):
        await self.send(text_data=json.dumps({
            'type': 'leaderboard',
            'leaderboard': event['leaderboard']
        }))

    async def send_question_with_leaderboard(self, event):
        await self.send(text_data=json.dumps({
            'type': 'question_with_leaderboard',
            'question': event['question'],
            'start_time': event['start_time'],
            'duration': event['duration'],
            'leaderboard': event['leaderboard']
        }))

    async def session_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'session_ended',
            'message': event['message']
        }))

    async def send_waiting_on(self, event):
        await self.send(text_data=json.dumps({
            'type': 'waiting_on',
            'players': event['players']
        }))

    async def reveal_answer(self, event):
        await self.send(text_data=json.dumps({
            'type': 'reveal_answer',
            'question_id': event['question_id'],
            'correct_option': event['correct_option'],
            'correct_participants': event['correct_participants'],
            'total_answers': event['total_answers'],
            'correct_count': event['correct_count']
        }))

    async def receive(self, text_data):
        data = json.loads(text_data)
        print("🟢 Received WebSocket message:", data)

        msg_type = data.get('type')  # ✅ Now it's defined

        if msg_type == 'push_question':
            await self.handle_push_question(data['question'])

        elif msg_type == 'reveal_answer':
            await self.handle_reveal_answer(data['question_id'], data['correct_option'])

        elif msg_type == 'end_session':
            await self.channel_layer.group_send(self.group_name, {
                'type': 'session_ended',
                'message': data.get('message', 'Session ended')
            })


    async def handle_push_question(self, question_data):
        question_id = question_data['id']
        correct_option = question_data.get('correct_option')
        duration = question_data.get('duration', 60)

        session = await database_sync_to_async(
            lambda: LiveSession.objects.get(session_code=self.session_code)
        )()

        # 🔧 Ensure LiveQuestion is created
        await database_sync_to_async(LiveQuestion.objects.create)(
            question_id=question_id,
            session=session
        )

        leaderboard = await self.get_leaderboard()

        await self.channel_layer.group_send(self.group_name, {
            'type': 'send_question_with_leaderboard',
            'question': question_data,
            'start_time': str(asyncio.get_event_loop().time()),
            'duration': duration,
            'leaderboard': leaderboard
        })

        await asyncio.sleep(duration)
        await self.handle_reveal_answer(question_id, correct_option)

    async def handle_reveal_answer(self, question_id, correct_option):
        if self.last_revealed_question_id == question_id:
            print(f"⏩ Skipping duplicate reveal for question {question_id}")
            return

        self.last_revealed_question_id = question_id

        # ✅ Correct filtering using foreign key field 'participant'
        correct_participants = await database_sync_to_async(
            lambda: list(
                ParticipantAnswer.objects
                .filter(question_id=question_id, selected_option=correct_option)
                .select_related('participant')  # optimize
                .values_list('participant__name', flat=True)
            )
        )()

        total_answers = await database_sync_to_async(
            lambda: ParticipantAnswer.objects.filter(question_id=question_id).count()
        )()

        await self.channel_layer.group_send(self.group_name, {
            'type': 'reveal_answer',
            'question_id': question_id,
            'correct_option': correct_option,
            'correct_participants': correct_participants,
            'total_answers': total_answers,
            'correct_count': len(correct_participants)
        })

        # ✅ Only get participants in this session
        list_of_player_names = await database_sync_to_async(
            lambda: list(
                Participant.objects
                .filter(session__session_code=self.session_code)
                .values_list('name', flat=True)
            )
        )()

        await self.channel_layer.group_send(self.group_name, {
            'type': 'send_waiting_on',
            'players': list_of_player_names
        })

    async def get_leaderboard(self):
        leaderboard_data = await database_sync_to_async(
            lambda: list(
                Participant.objects.filter(session__session_code=self.session_code)
                .annotate(correct_count=models.Count(
                    'participantanswer',
                    filter=models.Q(
                        participantanswer__selected_option=models.F('participantanswer__question__correct_option')
                    )
                ))
                .values('name', 'correct_count')
                .order_by('-correct_count')
            )
        )()
        return leaderboard_data
