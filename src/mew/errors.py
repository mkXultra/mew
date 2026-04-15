class MewError(Exception):
    pass


class ModelBackendError(MewError):
    pass


class CodexApiError(ModelBackendError):
    pass


class AnthropicApiError(ModelBackendError):
    pass
