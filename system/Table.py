from packages.tabulate import tabulate

class Table:
    __data = []
    __header = []
    __tableFormat = 'rounded_outline'

    def __init__(self, header = []):
        self.__header = header

    def addRow(self, data):
        self.__data.append(data)

    def setFormat(self, format):
        self.__tableFormat = format

    def setHeader(self, header):
        self.__header = header

    def build(self, data = None, headers = None, tableFormat = 'rounded_outline'):
        tableView = tabulate(
            tabular_data = data if data is not None else self.__data,
            headers = headers if headers is not None else self.__header,
            tablefmt = tableFormat if tableFormat is not None else self.__tableFormat,
            rowalign = 'center'
        )

        print(tableView)
