from aiogram.fsm.state import StatesGroup, State


class AddTeacherState(StatesGroup):
    name = State()
    subject = State()
    experience = State()
    bio = State()


class AddCourseState(StatesGroup):
    kind = State()
    name_uz = State()
    name_ru = State()
    name_en = State()
    description_uz = State()
    description_ru = State()
    description_en = State()
    icon = State()


class ReplyMessageState(StatesGroup):
    message_id = State()
    answer = State()


class AddLearningResourceState(StatesGroup):
    title = State()
    description = State()
    content = State()
    question = State()
    options = State()
    correct = State()
    explanation = State()
    next_question = State()


class UserManagementState(StatesGroup):
    search = State()
    reason = State()
    confirm = State()


class AdminAddState(StatesGroup):
    telegram_id = State()
    role = State()
    confirm = State()
