from fastapi import HTTPException, status


class CallServiceError(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(status_code=status_code, detail=detail)


class CallNotFoundError(CallServiceError):
    def __init__(self):
        super().__init__(detail="Chiamata non trovata", status_code=status.HTTP_404_NOT_FOUND)


class CallNotActiveError(CallServiceError):
    def __init__(self):
        super().__init__(detail="La chiamata non è più attiva", status_code=status.HTTP_400_BAD_REQUEST)


class NotAParticipantError(CallServiceError):
    def __init__(self):
        super().__init__(detail="Non sei un partecipante di questa chiamata", status_code=status.HTTP_403_FORBIDDEN)


class InsufficientPermissionsError(CallServiceError):
    def __init__(self):
        super().__init__(detail="Permessi insufficienti", status_code=status.HTTP_403_FORBIDDEN)


class AlreadyInCallError(CallServiceError):
    def __init__(self):
        super().__init__(detail="Sei già un partecipante di questa chiamata", status_code=status.HTTP_409_CONFLICT)


class UserNotFoundError(CallServiceError):
    def __init__(self):
        super().__init__(detail="Utente non trovato nel sistema", status_code=status.HTTP_404_NOT_FOUND)
