from aiogram.fsm.state import StatesGroup, State


class RegistrationState(StatesGroup):
    full_name = State()
    phone = State()
    course = State()
    level = State()
    preferred_time = State()
    message = State()
    confirm = State()


class SearchState(StatesGroup):
    query = State()


class SupportState(StatesGroup):
    topic = State()
    message = State()


class QuizState(StatesGroup):
    answering = State()
