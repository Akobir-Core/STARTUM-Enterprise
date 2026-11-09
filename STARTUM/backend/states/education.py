from aiogram.fsm.state import State, StatesGroup


class JoinGroupState(StatesGroup):
    code = State()


class CreateGroupState(StatesGroup):
    name = State()
    course = State()
    schedule = State()


class CreateHomeworkState(StatesGroup):
    group = State()
    title = State()
    instructions = State()


class SubmitHomeworkState(StatesGroup):
    homework = State()
    answer = State()


class AssignTeacherState(StatesGroup):
    telegram_id = State()
    course_id = State()
    group_id = State()
    confirm = State()


class ReviewSubmissionState(StatesGroup):
    grade = State()
    feedback = State()


class CreateAnnouncementState(StatesGroup):
    title_uz = State()
    title_ru = State()
    title_en = State()
    body_uz = State()
    body_ru = State()
    body_en = State()
