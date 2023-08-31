"""
/***************************************************************************
 EasyAttributeFilterValues
                                 A QGIS plugin
 検索およびリスト選択によるフィルター
                              -------------------
        copyright            : (C) 2021 by orbitalnet.inc
 ***************************************************************************/

"""
import os
import re

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QWidget, QMessageBox, QStyle, QTreeView
from qgis.PyQt.QtCore import pyqtSignal, Qt, QVariant, QSortFilterProxyModel, QModelIndex
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem

from qgis.gui import QgsAttributeTableFilterModel

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'easy_attribute_filter_values_base.ui'))

class EasyAttributeFilterValues(QWidget, FORM_CLASS):

    canceld = pyqtSignal()
    filterSet = pyqtSignal(str)

    def __init__(self, parent=None):
        super(EasyAttributeFilterValues, self).__init__(parent)

        self.setupUi(self)

        self.treeView.setRootIsDecorated(False)
        self.treeView.setItemsExpandable(False)
        self.treeView.setEditTriggers(QTreeView.NoEditTriggers)

        # 上限件数
        self.max_count = 1000

        self.field_name = ""
        self.is_numeric = True
        self.expression = ""

        # 検索ラインエディット
        self.filter_value_edit.setShowSearchIcon(True)
        self.filter_value_edit.setPlaceholderText("検索")

        # 既定件数超過警告ラベル＆アイコン
        label_textcolor = self.message_label.palette().windowText().color().name()
        self.message_label.setTextFormat(Qt.RichText)
        self.message_label.setText(f'<a href="./"><span style="color:{label_textcolor};">一部のデータは表示されていません</span></a>')
        self.message_label.setOpenExternalLinks(False)
        self.message_label.linkActivated.connect(self.openWarningLink)
        icon_size = self.icon_label.style().pixelMetric(QStyle.PM_SmallIconSize)
        self.icon_label.setPixmap(self.icon_label.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(icon_size, icon_size))
        self.showWarning(False)

        self.sample_model = QStandardItemModel(self)
        self.sample_model.itemChanged.connect(self.checkAll)

        self.proxy_model = TreeFilterSortProxyModel()
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.cancel_button.clicked.connect(lambda: self.canceld.emit())
        self.ok_button.clicked.connect(self.onOkClicked)
        self.filter_value_edit.valueChanged.connect(self.onFilterChanged)
        self.filter_value_edit.cleared.connect(self.onFilterCleared)

    def clear(self):
        self.treeView.setModel(None)
        self.proxy_model.setSourceModel(None)
        self.sample_model.clear()
        self.filter_value_edit.clearValue()

    def setValues(self, column: int, filter_model: QgsAttributeTableFilterModel, expression: str ):
        """
        地物の数値を取得して表示する
        """

        self.clear()

        # フィルターモデルの列からフィールドを特定する
        field_index, field = self.fieldFromColumn(column, filter_model)
        if field_index < 0:
            return

        self.field_name = field.name()
        self.is_numeric = field.isNumeric()

        (prev_is_null, phrase_in, prev_values) = self.parseExpression(expression)
        defaul_checked = len(expression) == 0 or phrase_in == False or (len(prev_values) == 0 and prev_is_null==False)

        # 対象レイヤーから指定列の固有値を取得する
        uniques = filter_model.layer().uniqueValues(field_index, self.max_count + 1)

        # データ件数超過の場合警告を表示する
        data_count = len(uniques) 
        if data_count > self.max_count:
            self.showWarning(True)
            data_count = self.max_count
        else:
            self.showWarning(False)

        self.sample_model.setColumnCount(2)

        has_null = False
        has_blank = False

        self.sample_model.blockSignals(True)

        # サンプル用のデータモデルを作成する
        root = self.createTreeItem("(すべて選択)", defaul_checked)
        root.setTristate(True)
        self.sample_model.appendRow(root)

        values = sorted(list(uniques))
        for row in range(0, data_count):
            value = values[row]

            if value is None or (isinstance(value, QVariant) and value.isNull()):
                has_null = True
                continue
            if self.is_numeric == False and len(str(value)) == 0:
                has_blank = True
                continue
            item = self.createTreeItem(str(value), defaul_checked or (value in prev_values))
            sub_item = QStandardItem(str(value))
            root.appendRow([item, sub_item])

        if has_null:
            item = self.createTreeItem("(NULL)", defaul_checked or prev_is_null)
            sub_item = QStandardItem("IS NULL")
            root.appendRow([item, sub_item])

        if has_blank:
            item = self.createTreeItem("(空白)", defaul_checked or ('' in prev_values))
            sub_item = QStandardItem("''")
            root.appendRow([item, sub_item])

        self.sample_model.blockSignals(False)

        self.proxy_model.setSourceModel(self.sample_model)
        self.treeView.setModel(self.proxy_model)
        self.treeView.setColumnHidden(1, True)
        self.treeView.expandAll()


    def createTreeItem(self, text: str, checked: bool):
        """
        QStandardItemを生成する
        """
        item = QStandardItem(text)
        item.setCheckable(True)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return item


    def fieldFromColumn(self, column: int, filter_model: QgsAttributeTableFilterModel):
        """
        フィールドを取得する
        """
        if filter_model is None:
            return (-1, None)
        if filter_model.actionColumnIndex() == column:
            return (-1, None)

        attribute_list = filter_model.layer().attributeList()
        if column < 0 or len(attribute_list) <= column:
            return (-1, None)

        field_index = attribute_list[column]
        return (field_index, filter_model.layer().fields().at(field_index))


    def parseExpression(self, expression: str) :
        """
        式を整形する
        """
        if len(expression) == 0:
            return (False, False, [])

        # NULLを含む
        pattern_null = re.compile(f'"{self.field_name}" IS NULL')
        included_null = pattern_null.match(expression) is None
        # IN () の中身
        pattern_in = re.compile(f'"{self.field_name}" IN \\((.+)\\)')
        matched = pattern_in.match(expression)
        if matched:
            values = matched.group(1).split(",")
            return_array = []
            if self.is_numeric:

                for v in values:
                    trimmed = v.strip()
                    if self.isInt(trimmed):
                        return_array.append(int(trimmed))
                    elif self.isFloat(trimmed):
                        return_array.append(float(trimmed))
                    else:
                        return_array.append(trimmed)
                
                return (included_null, True, return_array)
            else:
                for v in values:
                    return_array.append(v.strip().strip("'"))
                return (included_null, True, return_array)

        return (included_null, False, [])


    def isInt(self, text: str):
        """
        整数判定
        """
        pattern = '[-+]?\d+'
        return True if re.fullmatch(pattern, text) else False

    def isFloat(self, text: str):
        """
        Float判定
        """
        pattern = r'[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?'
        return True if re.fullmatch(pattern, text) else False

    def closeEvent(self, event):
        self.treeView.setModel(None)
        self.proxy_model.setSourceModel(None)
        self.sample_model.clear()

    def onFilterChanged(self, text: str):
        """
        Float判定
        """
        if len(text) > 0:
            self.proxy_model.setFilterRegExp(f".*{text}.*")
        else:
            self.proxy_model.setFilterRegExp("")

    def onFilterCleared(self):
        """
        Float判定
        """
        self.proxy_model.setFilterRegExp("")
        
    def onOkClicked(self):
        """
        Float判定
        """

        "式の作成"
        if self.proxy_model.rowCount() == 0:
            self.expression = ""
            return

        values = []
        has_null = False
        for root_row in range(0, self.proxy_model.rowCount()):
            root_index = self.proxy_model.index(root_row, 0, QModelIndex())

            if self.proxy_model.hasChildren(root_index) == False:
                continue

            children_count = self.proxy_model.rowCount(root_index)
            for row in range(0, children_count):
                child_checked = self.proxy_model.data(self.proxy_model.index(row, 0, root_index), Qt.CheckStateRole)
                if child_checked == Qt.Checked:
                    child1 = str(self.proxy_model.data(self.proxy_model.index(row, 0, root_index), Qt.DisplayRole))
                    child2 = str(self.proxy_model.data(self.proxy_model.index(row, 1, root_index), Qt.DisplayRole))
                    
                    if child1 == "(NULL)" and child2 == "IS NULL":
                        has_null = True
                    else:
                        value_text = child2
                        if self.is_numeric or value_text == "''":
                            values.append(value_text)
                        else:
                            values.append(f"'{value_text}'")

        if len(values) == 0:
            self.expression = ""
            return
        
        values_joined = ",".join(values)

        if len(values) > 0:
            if has_null:
                self.expression = f'("{self.field_name}" IN ({values_joined}) OR "{self.field_name}" IS NULL)'
            else:
                self.expression = f'"{self.field_name}" IN ({values_joined})'
        else:
            if has_null:
                self.expression = f'"{self.field_name}" IS NULL'

        self.filterSet.emit(self.expression)


    def checkAll(self, item):
        """
        すべてチェック
        """
        checked = item.checkState()
        if item.hasChildren():
            if item.checkState() == Qt.PartiallyChecked:
                return

            # 全ての子供のチェックを同じにする
            row_count = item.rowCount()
            for row in range(0, row_count):
                if item.child(row).checkState() != checked:
                    item.child(row).setCheckState(checked)
        else:
            # 親のチェックを連動させる
            parent = item.parent()
            if parent:
                has_unchecked = False
                has_checked = False
                row_count = parent.rowCount()
                for row in range(0, row_count):
                    if parent.child(row).checkState() == Qt.Unchecked:
                        has_unchecked = True
                    elif parent.child(row).checkState() == Qt.Checked:
                        has_checked = True

                    if has_unchecked and has_checked:
                        break

                if has_unchecked and has_checked:
                    if parent.checkState() != Qt.PartiallyChecked:
                        parent.setCheckState(Qt.PartiallyChecked)
                elif has_checked and has_unchecked == False:
                    if parent.checkState() != Qt.Checked:
                        parent.setCheckState(Qt.Checked)
                elif has_unchecked and has_checked == False:
                    if parent.checkState() != Qt.Unchecked:
                        parent.setCheckState(Qt.Unchecked)

    def showWarning(self, flg: bool=False):
        """
        メッセージの表示有無を設定
        """
        self.message_label.setVisible(flg)
        self.icon_label.setVisible(flg)
    

    def openWarningLink(self, link: str):
        """
        warning表示
        """
        QMessageBox.warning(self.parentWidget(), "警告", f"このフィールドには、{self.max_count:,}個を超える固有のアイテムが存在します。\n{self.max_count:,}番目までのアイテムが表示されます。")


class TreeFilterSortProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        if self.filterRegExp().isEmpty():
            return True

        index = self.sourceModel().index(source_row, 0, source_parent)

        if self.sourceModel().hasChildren(index):
            return True

        return super().filterAcceptsRow(source_row, source_parent)