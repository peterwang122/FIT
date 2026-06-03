from pydantic import BaseModel


class PhddnsWatchdogStatusResponse(BaseModel):
    installed: bool
    enabled: bool
    running: bool
    pid: int | None = None
    last_exit_status: int | None = None
    label: str
    plist_path: str
    log_lines: list[str] = []
    message: str = ""


class PhddnsWatchdogTogglePayload(BaseModel):
    enabled: bool
