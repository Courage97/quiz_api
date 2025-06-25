from django.urls import path
from .views import *
from .views import register_host
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('register/host/', register_host),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('quizzes/', QuizListCreateView.as_view()),
    path('quizzes/<int:pk>/', QuizDetailView.as_view()),
    path('questions/', QuestionListCreateView.as_view()),
    path('quizzes/<int:pk>/questions/', quiz_questions_view),
    path('questions/<int:pk>/', QuestionDetailView.as_view()),
    path('sessions/', LiveSessionCreateView.as_view()),
    path('join/', join_session),
    path('sessions/<str:code>/push-question/', push_question),
    path('answers/', ParticipantAnswerCreateView.as_view()),
    path('sessions/<str:code>/results/', session_results),
    path('feedback/', feedback_create),
    path('sessions/<str:code>/summary/', session_summary),
    path('sessions/<str:code>/participant-summary/', participant_summary),


]
