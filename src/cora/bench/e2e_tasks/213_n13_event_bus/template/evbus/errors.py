class DispatchError(Exception):
    def __init__(self, errors: list[tuple[int, BaseException]]) -> None:
        super().__init__(f"{len(errors)} handler(s) failed")
        self.errors = errors
