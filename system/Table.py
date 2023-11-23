from packages.tabulate import tabulate


class Table:
    __data = []
    __header = []
    __tableFormat = "rounded_outline"

    def __init__(self, header: list = []) -> None:
        self.__header = header

    def add_row(self, data: {list, dict}) -> None:
        self.__data.append(data)

    def set_format(self, format: str) -> None:
        self.__tableFormat = format

    def set_header(self, header: list) -> None:
        self.__header = header

    def build(self, data: {list, dict}=None, headers: list = None, table_format: str = "rounded_outline") -> None:
        table_view = tabulate(
            tabular_data=data if data is not None else self.__data,
            headers=headers if headers is not None else self.__header,
            tablefmt=table_format if table_format is not None else self.__tableFormat,
            rowalign="center",
        )

        print(table_view)
