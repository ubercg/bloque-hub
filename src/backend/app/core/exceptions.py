from fastapi import HTTPException

# Assuming DomainException exists, if not, I'd use HTTPException or a custom base
class DomainException(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

class InvalidStateTransitionError(DomainException):
    def __init__(self, current_status: str, target_status: str, detail: str = "Invalid state transition"):
        super().__init__(status_code=400, detail=f"{detail}: Cannot transition from {current_status} to {target_status}")


class SoDViolationException(DomainException):
    def __init__(self, detail: str = "Segregation of Duties violation: User role is not permitted to perform this action."):
        super().__init__(status_code=403, detail=detail)
