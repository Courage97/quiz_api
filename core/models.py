from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta

# ─── Custom User ──────────────────────────────────────

class User(AbstractUser):
    is_host = models.BooleanField(default=False)

    def __str__(self):
        return self.username


# ─── Quiz and Questions ──────────────────────────────

class Quiz(models.Model):
    title = models.CharField(max_length=150)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    option_a = models.CharField(max_length=200)
    option_b = models.CharField(max_length=200)
    option_c = models.CharField(max_length=200, blank=True, null=True)
    option_d = models.CharField(max_length=200, blank=True, null=True)
    correct_option = models.CharField(max_length=1, choices=[('A','A'), ('B','B'), ('C','C'), ('D','D')])
    is_true_false = models.BooleanField(default=False)  # If it's a T/F question

    def __str__(self):
        return f"{self.text[:40]}..."


# ─── Live Quiz Session ───────────────────────────────

class LiveSession(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    host = models.ForeignKey(User, on_delete=models.CASCADE)
    session_code = models.CharField(max_length=8, unique=True)
    is_active = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def end(self):
        self.is_active = False
        self.ended_at = timezone.now()
        self.save()

    def __str__(self):
        return f"Session {self.session_code} - {self.quiz.title}"


# ─── Participants ─────────────────────────────────────

class Participant(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100)
    score = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} in {self.session.session_code}"


# ─── Live Questions (one per round) ──────────────────

class LiveQuestion(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    displayed_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.IntegerField(default=60)  # timer per question
    displayed_at = models.DateTimeField(auto_now_add=True)

    @property
    def expires_at(self):
        return self.displayed_at + timedelta(seconds=self.duration_seconds)

    def is_active(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.question.text[:60]} in {self.session.session_code}"


# ─── Participant Answer ───────────────────────────────

class ParticipantAnswer(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1)
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('participant', 'question')

    def __str__(self):
        return f"{self.participant.name} answered {self.question.id}"


# ─── Feedback / Review ────────────────────────────────

class Feedback(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    comments = models.TextField()
    rating = models.PositiveSmallIntegerField()  # Add this missing field
    # submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback by {self.participant.name}"