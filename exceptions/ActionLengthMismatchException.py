from system.Cli import Cli


class ActionLengthMismatchException(BaseException):
    def __init__(self, expected_length):
        self.expected_length = expected_length
        pass

    def __new__(*cls, **kwargs):
        cli = Cli()

        expected_length = cls[1]
        provided_length = len(cli.get_actions())

        cli.print_error(f"Exactly {expected_length} arguments were excepted, but {provided_length} provided.")

        raise SystemExit
