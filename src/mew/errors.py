class MewError(Exception):
    pass


class ModelBackendError(MewError):
    pass


class ModelRefusalError(ModelBackendError):
    pass


class CodexApiError(ModelBackendError):
    pass


class CodexRefusalError(CodexApiError, ModelRefusalError):
    pass


class AnthropicApiError(ModelBackendError):
    pass
