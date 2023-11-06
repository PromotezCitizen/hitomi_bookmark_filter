from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit

class InputDataImformationDialog(QDialog):
    def __init__(self, data, oper):
        super().__init__()
        self.__data = data  # 메인 다이얼로그 객체 전달 받음
        self.__type = oper

        self.__text_edit = QTextEdit("")
        self.__text_edit.setReadOnly(True)

        self.initUI()

    def initUI(self):
        self.setWindowTitle("입력 데이터")

        self.setGeometry(300, 300, 600, 600)

        layout = QVBoxLayout()
        if self.__type == "e":
            self.__setLabelWithExceptionTag()
        elif self.__type == "b":
            self.__setLabelWithBookmark()

        layout.addWidget(self.__text_edit)
        self.setLayout(layout)

    def __setLabelWithExceptionTag(self):
        self.__text_edit.setPlainText("\n\n".join(self.__data))

    def __setLabelWithBookmark(self):
        temp = [ bookmark['url'] for bookmark in self.__data ]
        self.__text_edit.setPlainText("\n\n".join(temp))