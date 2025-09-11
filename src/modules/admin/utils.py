
import contextvars

my_context_var = contextvars.ContextVar('processing_error', default='')


def custom_greeting() -> str:
    current_error = my_context_var.get()
    return f"Error detected: '{current_error=}'"
