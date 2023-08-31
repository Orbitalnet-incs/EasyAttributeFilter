"""
/***************************************************************************
 EasyAttributeFilterOptionDialog
                                 A QGIS plugin
 検索簡易フィルターオプションダイアログ
                              -------------------
        copyright            : (C) 2023 by orbitalnet.inc
 ***************************************************************************/

"""
import os
import re
from typing import Union

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QStandardItemModel, QStandardItem

from qgis.core import QgsMessageLog, QgsApplication
from qgis.gui import QgsAttributeTableFilterModel

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'easy_attribute_filter_option_dialog_base.ui'))

NUMERIC_OPERATORS = {"と等しい": "=","と等しくない": "!=","より大きい": ">","以上": ">=","より小さい": "<","以下": "<="}
TEXT_OPERATORS  = {"で始まる": "LIKE '(value)%'","で始まらない": "NOT LIKE '(value)%'","で終わる": "LIKE '%(value)'","で終わらない": "NOT LIKE '%(value)'","を含む": "LIKE '%(value)%'","を含まない": "NOT LIKE '%(value)%'"}

class EasyAttributeFilterOptionDialog(QtWidgets.QDialog, FORM_CLASS):
    
    def __init__(self, parent=None, flags: Union[Qt.WindowFlags, Qt.WindowType] = Qt.WindowFlags()):
        super(EasyAttributeFilterOptionDialog, self).__init__(parent, flags)

        self.setupUi(self)

        # 上限件数
        self.max_count = 1000

        self.field_name = ""
        self.is_numeric = True
        self.expression = ""

        self.sample_model = QStandardItemModel(self)

        self.setOperators()

    def setValues(self, column: int, filter_model: QgsAttributeTableFilterModel, expression: str):
        """
        値を設定する
        
        @param  column:列番号
        @param  filter_model:フィルターモデル
        @param  expression:式
        """
        QgsApplication.setOverrideCursor(Qt.WaitCursor)

        self.value_combobox1.setModel(None)
        self.value_combobox2.setModel(None)
        self.sample_model.clear()

        # 属性情報を取得する
        field_index, field = self.fieldFromColumn(column, filter_model)
        self.field_name = field.name()
        if self.is_numeric != field.isNumeric():
            self.is_numeric = field.isNumeric()
            # 演算子コンボボックスを再作成する
            self.setOperators()

        self.sample_label.setText(self.field_name)
        
        # 対象レイヤーから指定列の固有値を取得する
        uniques = filter_model.layer().uniqueValues(field_index, self.max_count)

        # データ件数超過の場合警告を表示する
        data_count = len(uniques) 

        self.sample_model.setColumnCount(1)

        # サンプル用のデータモデルを作成する
        values = sorted(list(uniques))
        self.sample_model.appendRow(QStandardItem(""))

        for row in range(0, data_count):
            item = QStandardItem(str(values[row]))
            self.sample_model.appendRow(item)
        
        self.value_combobox1.setModel(self.sample_model)
        self.value_combobox2.setModel(self.sample_model)

        # テキスト式入力欄を作成する
        self.setTextExpression(expression)

        QgsApplication.restoreOverrideCursor()


    def fieldFromColumn(self, column: int, filter_model: QgsAttributeTableFilterModel) :
        """
        属性indexと属性を取得する
        
        @param  column:列番号
        @param  filter_model:フィルターモデル
        """
        if filter_model is None:
            return (-1, None)
        if filter_model.actionColumnIndex() == column:
            return (-1, None)

        attribute_list = filter_model.layer().attributeList()
        if column < 0 or len(attribute_list) <= column:
            return (-1, None)

        field_index = attribute_list[column]
        return field_index, filter_model.layer().fields().at(field_index)

    def setOperators(self):
        """
        演算子を設定する
        """
        self.operator_combobox1.clear()
        self.operator_combobox2.clear()

        for op_num in NUMERIC_OPERATORS.keys():
            self.operator_combobox1.addItem(op_num)
            self.operator_combobox2.addItem(op_num)

        if self.is_numeric == False:
            for op_text in TEXT_OPERATORS.keys():
                self.operator_combobox1.addItem(op_text)
                self.operator_combobox2.addItem(op_text)

    def accept(self):
        """
        処理の実行
        """
        self.expression = ""

        # 入力チェック
        if self.checkInput() == False:
            return

        # 式を生成する
        self.expression = self.createExpression(self.operator_combobox1.currentText(), self.value_combobox1.currentText())

        if len(self.value_combobox2.currentText()) > 0 and len(self.operator_combobox2.currentText()) > 0:
            logical_operator = "AND" if self.and_radiobutton.isChecked() else "OR"

            self.expression += f" {logical_operator} {self.createExpression(self.operator_combobox2.currentText(), self.value_combobox2.currentText())}"

        return super().accept()
    
    def createExpression(self, operator: str, value: str) -> str:
        """
        式を生成する

        @param  operator:演算子
        @param  value:判定値

        @return 式
        """
        if operator in NUMERIC_OPERATORS:
            return f"\"{self.field_name}\" {NUMERIC_OPERATORS[operator]} {self.enclosedQuotes(value)}"

        elif operator in TEXT_OPERATORS:
            pattern = TEXT_OPERATORS[operator]
            like_pattern = pattern.replace("(value)", value)
            return f"\"{self.field_name}\" {like_pattern}"

        return ""

    def enclosedQuotes(self, value):
        return value if self.is_numeric else f"'{value}'"

    def checkInput(self) -> bool:
        """
        入力チェック

        @return bool True:有効、False:エラー
        """
        operator1 = self.operator_combobox1.currentText()
        if len(self.value_combobox1.currentText()) == 0 and len(operator1) == 0:
            self.operator_combobox1.setFocus()
            QtWidgets.QMessageBox.warning(self.parentWidget(), "エラー", "入力にエラーがあります。")
            return False

        if self.is_numeric:
            if len(self.value_combobox1.currentText()) == 0 and len(operator1) > 0:
                self.value_combobox1.setFocus()
                QtWidgets.QMessageBox.warning(self.parentWidget(), "エラー", "入力にエラーがあります。")
                return False
        
            if len(self.value_combobox2.currentText()) == 0 and len(self.operator_combobox2.currentText()) > 0:
                self.value_combobox2.setFocus()
                QtWidgets.QMessageBox.warning(self.parentWidget(), "エラー", "入力にエラーがあります。")
                return False

        return True

    def setTextExpression(self, expression: str):
        """
        テキスト式入力欄を作成する

        @param  expression:式
        """
        if len(expression) == 0:
            self.value_combobox1.setCurrentIndex(0)
            self.value_combobox2.setCurrentIndex(0)
            self.operator_combobox1.setCurrentIndex(0)
            self.operator_combobox2.setCurrentIndex(0)
            return

        pattern_dual = re.compile(f"^(.+) (AND|OR) (.+)$")
        match_dual = pattern_dual.fullmatch(expression)
        if match_dual:
            # ２つ用
            expression1 = match_dual.group(1)
            and_or = match_dual.group(2)
            expression2 = match_dual.group(3)

            QgsMessageLog.logMessage(f"DUAL expression1={expression1} expression2={expression2}")

            if and_or == "OR":
                self.or_radiobutton.setChecked(True)
            else:
                self.and_radiobutton.setChecked(True)

            self.parseExpression(expression1, self.value_combobox1, self.operator_combobox1)
            self.parseExpression(expression2, self.value_combobox2, self.operator_combobox2)

        else:
            self.parseExpression(expression, self.value_combobox1, self.operator_combobox1)

    def parseExpression(self, expression: str, value_combobox: QtWidgets.QComboBox, operator_combobox: QtWidgets.QComboBox ):
        """
        式を解析して、コンボボックスに設定する

        @param  expression:式
        @param  value_combobox:設定する判定値コンボボックス
        @param  operator_combobox:設定する演算子コンボボックス
        """
        while True:
            expression_ = expression.strip()
            if len(expression_) == 0:
                break

            pattern1 = re.compile(r"\"(\w+)\" (=|!=|>|>=|<|<=) (.+)")
            match1 = pattern1.fullmatch(expression_)
            if match1:
                operator1 = match1.group(2)
                value1 = match1.group(3).strip("'")


                keys1 = [k1 for k1, v1 in NUMERIC_OPERATORS.items() if v1 == operator1]
                if len(keys1) > 0:
                    key1 = keys1[0]
                    value_combobox.setEditText(value1)
                    operator_combobox.setCurrentIndex(operator_combobox.findText(key1))
                    return
                
            pattern2 = re.compile(r"\"(\w+)\" (LIKE|NOT LIKE) (.+)")
            match2 = pattern2.fullmatch(expression_)
            if match2:
                operator2 = match2.group(2)
                value2 = match2.group(3).strip("'")

                search_value = "(value)"
                if value2.startswith("%"):
                    search_value = "%" + search_value
                if value2.endswith("%"):
                    search_value = search_value + "%"

                search_value = f"{operator2} '{search_value}'"
                value2 = value2.strip("%")

                keys2 = [k2 for k2, v2 in TEXT_OPERATORS.items() if v2 == search_value]
                if len(keys2) > 0:
                    key2 = keys2[0]
                    value_combobox.setEditText(value2)
                    operator_combobox.setCurrentIndex(operator_combobox.findText(key2))
                    return

            break

        value_combobox.setCurrentText("")
        operator_combobox.setCurrentIndex(0)
