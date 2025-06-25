The Interview Quiz Platform (Backend) leverages Django and Django REST Framework to power its real-time, quiz-based interactions. 
It manages key components like user authentication, quiz and question models, live session tracking, and participant scoring with clarity and efficiency. 
The backend exposes secure RESTful endpoints for creating quizzes, submitting answers, and retrieving results, all protected through JWT-based authentication. 
Its architecture supports real-time communication via WebSocket (Channels), enabling instantaneous question delivery and answer reveal events during live sessions.
Each submitted answer undergoes validation—checking session state, preventing duplicate responses, and scoring correctness—before updating participant scores atomically. 
Additionally, session summary and feedback data are aggregated for hosts to review post-session. 
This backend is production-ready: it’s containerized with Docker, supports horizontal scaling, and cleanly separates concerns so that it's easy to extend—for example, 
adding new question types or analytics. The result is a robust system that ensures data integrity, real-time responsiveness, and administrative insight through a well-defined API layer.

