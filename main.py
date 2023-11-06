import sys
from PyQt5.QtWidgets import QComboBox, QWidget, QLabel, QPushButton, QGridLayout, QFileDialog, QApplication
import mimetypes
import json
import re
import multiprocessing

from information import InputDataImformationDialog
from logic import SearchLogic

class HentoidWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.__exception_tag_path_label = QLabel("")
        self.__exception_tag_path_label.setWordWrap(True)
        # self.__exception_tag_path_label.setStyleSheet("border: 2px solid black;")  # 외곽선 스타일 설정
        self.__exception_tag_btn = QPushButton('불러오기')
        self.__exception_tag_btn.clicked.connect(self.__getExceptionTag)
        self.__exception_tag_description_btn = QPushButton('제외 리스트')
        self.__exception_tag_description_btn.clicked.connect(self.__showList)

        self.__bookmark_path_label = QLabel("")
        self.__bookmark_path_label.setWordWrap(True)
        # self.__bookmark_path_label.setStyleSheet("border: 2px solid black;")  # 외곽선 스타일 설정
        self.__bookmark_btn = QPushButton('불러오기')
        self.__bookmark_btn.clicked.connect(self.__getBookmark)
        self.__bookmark_description_btn = QPushButton('북마크 리스트')
        self.__bookmark_description_btn.clicked.connect(self.__showList)

        
        self.__run_btn = QPushButton("실행")
        self.__run_btn.clicked.connect(self.__run)

        self.__cb = QComboBox(self)
        self.__cpu_label = QLabel("")

        self.__pexception_tag = None
        self.__bookmark = None
        self.__bookmark_filename = None

        self.__cpu = 16
        self.__cpu_label.setText(str(self.__cpu))

        self.COLUMN = 6

        self.DEFAULT = 2
        self.GRID1 = self.DEFAULT*0
        self.GRID2 = self.DEFAULT*1
        self.GRID3 = self.DEFAULT*2

        self.__bookmark_btn_enable = False
        self.__exception_tag_btn_enable = False

        self.__pattern = r'^[a-zA-Z]+:[a-zA-Z]+$'

        self.initUI()

    def initUI(self):
        grid = QGridLayout()

        grid.addWidget(QLabel('제외항목'), self.GRID1, 0)
        grid.addWidget(self.__exception_tag_path_label, self.GRID1, 1, 1, self.COLUMN-3)
        grid.addWidget(self.__exception_tag_btn, self.GRID1, self.COLUMN-2)
        grid.addWidget(self.__exception_tag_description_btn, self.GRID1, self.COLUMN-1)

        grid.addWidget(QLabel('북마크 파일'), self.GRID2, 0)
        grid.addWidget(self.__bookmark_path_label, self.GRID2, 1, 1, self.COLUMN-3)
        grid.addWidget(self.__bookmark_btn, self.GRID2, self.COLUMN-2)
        grid.addWidget(self.__bookmark_description_btn, self.GRID2, self.COLUMN-1)

        grid.addWidget(self.__run_btn, self.GRID3, 2, 1, self.COLUMN-4)
        
        for i in range(multiprocessing.cpu_count(), 0, -1):
            self.__cb.addItem(str(i))
        self.__cb.activated[str].connect(self.__setCpucount)

        grid.addWidget(self.__cb, self.GRID3, self.COLUMN-2)
        grid.addWidget(self.__cpu_label, self.GRID3, self.COLUMN-1)

        self.__exception_tag_description_btn.setEnabled(False)
        self.__bookmark_description_btn.setEnabled(False)
        self.__run_btn.setEnabled(False)
        
        self.setLayout(grid)

        self.setWindowTitle('QGridLayout')
        self.move(300, 300)
        self.setFixedSize(600, 300)

    def __setCpucount(self, data):
        self.__cpu = int(data)
        self.__cpu_label.setText(data)

    def __getExceptionTag(self):
        try:
            fname = self.__getFilename()
            if not fname:
                raise ValueError('file must be inputted!!!!!')
            if self.__determineExtention(fname) != 'plain':
                raise ValueError('exception tags file must be a text file')
            self.__changeExceptionTagPath(fname)

            self.__getExceptionList(fname)

            if not self.__isValidExceptionTag():
                raise ValueError('exception tag must have pattern: ***:***')
            self.__exception_tag_description_btn.setEnabled(True)
            self.__exception_tag_btn_enable = True
        except:
            self.__changeExceptionTagPath()
            self.__exception_tag = None
            self.__exception_tag_description_btn.setEnabled(False)
            self.__exception_tag_btn_enable = False
        finally:
            self.__canEnableRunBtn()

    def __getBookmark(self):
        try:
            fname = self.__getFilename()
            self.__bookmark_filename = fname
            if not fname:
                raise ValueError('file must be inputted!!!!!')
            if self.__determineExtention(fname) != 'json':
                raise ValueError('bookmark file must be a json file')
            self.__changeBookmarkPath(fname)

            self.__getBookmarkJson(fname)
            self.__bookmark_description_btn.setEnabled(True)
            self.__bookmark_btn_enable = True
        except:
            self.__changeBookmarkPath()
            self.__bookmark = None
            self.__bookmark_description_btn.setEnabled(False)
            self.__bookmark_filename = None
            self.__bookmark_btn_enable = False
        finally:
            self.__canEnableRunBtn()
    

    def __getFilename(self):
        return QFileDialog.getOpenFileName(self, 'Open file', './')[0]
    
    def __getExceptionList(self, fname):
        with open(fname, 'r') as f:
            exceptions = f.readlines()
        temp = list(filter(lambda tag: tag.strip() != "", exceptions))
        self.__exception_tag = [ tag.strip() for tag in temp ]

    def __getBookmarkJson(self, fname):
        with open(fname, 'r', encoding="utf-8") as f:
            self.__bookmark = json.load(f)['bookmarks']

    def __changeExceptionTagPath(self, fname=""):
        self.__exception_tag_path_label.setText(fname)

    def __changeBookmarkPath(self, fname=""):
        self.__bookmark_path_label.setText(fname)

    def __showList(self):
        sender_btn = self.sender()
        btn_name = sender_btn.text().split(' ')[0]

        if btn_name == '제외' and self.__exception_tag:
            self.__showExceptionTag()
        elif btn_name == '북마크' and self.__bookmark:
            self.__showBookmark()

    def __showExceptionTag(self):
        self.__modal = InputDataImformationDialog(data=self.__exception_tag, oper="e")
        self.__modal.exec_()

    def __showBookmark(self):
        self.__modal = InputDataImformationDialog(data=self.__bookmark, oper="b")
        self.__modal.exec_()

    def __isValidExceptionTag(self):
        return sum([ bool(re.match(self.__pattern, tag)) for tag in self.__exception_tag ]) == len(self.__exception_tag)

    def __canEnableRunBtn(self):
        enabled = self.__bookmark_btn_enable and self.__exception_tag_btn_enable
        self.__run_btn.setEnabled(enabled)

    def __determineExtention(self, fname):
        data = mimetypes.guess_type(fname)
        return data[0].split('/')[1]
    
    def __run(self):
        logic = SearchLogic(16)
        logic.setBookmark(self.__bookmark)
        logic.setExceptionTag(self.__exception_tag)
        logic.setFilename(self.__bookmark_filename)

        logic.run()
        del logic
        pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = HentoidWindow()
    ex.show()
    sys.exit(app.exec_())