# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EasyAttributeFilterDialog
                                 A QGIS plugin
 検索簡易フィルターダイアログ
                             -------------------
        copyright            : (C) 2023 by orbitalnet.inc
 ***************************************************************************/

"""

import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMenu, QAction, QWidgetAction
from qgis.PyQt.QtCore import pyqtSignal, Qt, QPoint
from qgis.PyQt.QtGui import QCursor, QColor

from qgis.core import *
from qgis.gui import *

from .easy_attribute_filter_values import EasyAttributeFilterValues
from .easy_attribute_filter_option_dialog import EasyAttributeFilterOptionDialog

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'easy_attribute_filter_dialog_base.ui'))

class EasyAttributeFilterDialog(QDialog, FORM_CLASS):

    closed = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(EasyAttributeFilterDialog, self).__init__(parent, Qt.Dialog | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.iface = iface

        # 選択可能なレイヤーを設定
        self.vectorlayer_combobox.setFilters(QgsMapLayerProxyModel.VectorLayer)

        # テーブルヘッダに独自のコンテキストメニューを表示する
        self.table_view.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.horizontalHeader().customContextMenuRequested.connect(self.showHeaderContextMenu)

        # connect設定
        # レイヤー変更
        self.vectorlayer_combobox.layerChanged.connect(self.updateTableData)
        # フィルタークリアボタン
        self.filter_clear_button.clicked.connect(self.clearAllFilters)
        # 地図表示
        self.zoom_features_button.clicked.connect(self.zoomToFeature)
        # 閉じるボタン
        self.close_button.clicked.connect(lambda: self.close())
        # プロジェクト変更
        QgsProject.instance().homePathChanged.connect(lambda: self.close())

        # コンテキストメニュー
        self.menu = QMenu(self)
        self.action_sort_ascending = QAction("昇順", self)
        self.action_sort_ascending.triggered.connect(lambda: self.sort(True))
        self.menu.addAction(self.action_sort_ascending)

        self.action_sort_descending = QAction("降順", self)
        self.action_sort_descending.triggered.connect(lambda: self.sort(False))
        self.menu.addAction(self.action_sort_descending)

        self.action_option_filter = QAction("テキストフィルター", self)
        self.action_option_filter.triggered.connect(self.showOptionFilterDialog)
        self.menu.addAction(self.action_option_filter)

        self.action_clear_filter = QAction("フィルタ クリア", self)
        self.action_clear_filter.triggered.connect(self.clearFieldFilter)
        self.menu.addAction(self.action_clear_filter)

        # 検索およびリスト選択によるフィルター
        self.filter_values = EasyAttributeFilterValues()
        self.filter_values.canceld.connect(lambda: self.menu.close())
        self.filter_values.filterSet.connect(self.setFieldFilterFromPopup)
        self.action_filter_editor = QWidgetAction(self)
        self.action_filter_editor.setDefaultWidget(self.filter_values)
        self.menu.addAction(self.action_filter_editor)
        self.menu.aboutToHide.connect(lambda: self.filter_values.clear())

        # 変数初期化
        self.field_filters = dict()
        self.column_target = -1
        self.layer = None
        self.filter_model = None
        self.master_model = None
        self.layer_cache = None


    def clear(self):
        """
        クリア
        """        
        self.field_filters.clear()
        self.table_view.setModel(None)
        self.table_view.setFeatureSelectionManager(None)
        self.filter_model = None
        self.layer = None
        self.master_model = None
        self.layer_cache = None


    def updateTableData(self, layer: QgsMapLayer):
        """
        表示内容を更新する
        
        @param  layer:選択したレイヤ
        """

        # 変数クリア
        self.clear()

        # レイヤ有効性チェック
        self.layer = layer if layer is not None else self.iface.layerTreeView().currentLayer()
        if self.layer is None:
            return
        if self.layer.type() != QgsMapLayerType.VectorLayer :
            self.layer = None
            return

        # カーソルを待機中にする
        QgsApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # レイヤキャッシュを作成
        self.initLayerCache()

        # データテーブル初期化   
        self.initModels()
        self.table_view.setAttributeTableConfig(self.vectorlayer_combobox.currentLayer().attributeTableConfig())
        self.table_view.setModel(self.filter_model)

        # カーソルを戻す
        QgsApplication.restoreOverrideCursor()


    def showEvent(self, event):
        """
        表示処理
        """
        if self.windowState() != Qt.WindowMinimized:
            if QgsProject.instance().count() > 0:
                if self.iface.layerTreeView().currentLayer() is not None:
                    # 現在のレイヤを選択
                    self.vectorlayer_combobox.setEnabled(True)
                    self.table_view.setEnabled(True)
                    self.vectorlayer_combobox.setLayer(self.iface.layerTreeView().currentLayer())
                    return

            # 現在プロジェクトにひとつもレイヤーがない場合は各ウィジェットを使用不可にして空の状態で表示する
            self.vectorlayer_combobox.setEnabled(False)
            self.table_view.setEnabled(False)


    def initLayerCache(self):
        """
        選択レイヤの地物のキャッシュを作成する
        """
        # 属性表示時の標準キャッシュサイズを取得する
        settings = QgsSettings()
        cache_size = int(settings.value("qgis/attributeTableRowCache", "10000" ))

        # 選択レイヤのキャッシュを作成する
        self.layer_cache = QgsVectorLayerCache(self.layer, cache_size)
        self.layer_cache.setCacheGeometry(False)

        if 0 == cache_size or  0 == ( QgsVectorDataProvider.SelectAtId & self.layer.dataProvider().capabilities() ):
            # キャッシュサイズが0だったり、地物IDで地物にアクセスできない場合は全地物をキャッシュする
            self.layer_cache.setFullCache(True)


    def initModels(self):
        """
        属性データモデルを作成
        """
        self.filter_model = None
        self.master_model = None

        self.master_model = QgsAttributeTableModel(self.layer_cache, self)
        self.master_model.setRequest(QgsFeatureRequest())
        self.master_model.loadLayer()

        self.filter_model = QgsAttributeTableFilterModel(self.iface.mapCanvas(), self.master_model, self)


    def clearAllFilters(self):
        """
        フィルタークリア（一覧）
        """
        for column in self.field_filters.keys():
            self.filter_model.setHeaderData(column, Qt.Horizontal, QColor(), Qt.ForegroundRole)
        self.field_filters.clear()

        # クリア後に再表示
        self.showAll()


    def zoomToFeature(self):
        """
        選択した地物にズーム
        """
        if self.layer:
            self.iface.mapCanvas().zoomToSelected(self.layer)


    def clearFieldFilter(self):
        """
        フィルタークリア（ポップアップ）
        """
        if self.column_target in self.field_filters:
            del self.field_filters[self.column_target]
            self.filter_model.setHeaderData(self.column_target, Qt.Horizontal, QColor(), Qt.ForegroundRole)
            # 全体のフィルタを作成し再設定する
            self.filterFeatures()


    def sort(self, ascending: bool=True):
        """
        並び替え

        @param  ascending:昇順or降順
        """
        if self.vectorlayer_combobox.currentLayer() is None:
            return

        if self.filter_model is None:
            return

        provider = self.vectorlayer_combobox.currentLayer().dataProvider()
        if provider is None:
            return

        self.filter_model.sort(self.column_target, Qt.AscendingOrder if ascending else Qt.DescendingOrder)
        

    def showOptionFilterDialog(self):
        """
        テキストフィルターダイアログ表示
        """

        dlg = EasyAttributeFilterOptionDialog(self)
        
        # 前回設定したフィルターがあるか確認
        previous_filter = self.field_filters.get(self.column_target, "")

        # 対象列からフィールドを特定する
        dlg.setValues(self.column_target, self.filter_model, previous_filter)
        
        if dlg.exec() != QDialog.Accepted:
            return

        # フィルター式を保管する
        self.setFieldFilter(self.column_target, dlg.expression)
        # 全体のフィルタを作成し再設定する
        self.filterFeatures()


    def setFieldFilterFromPopup(self, expression):
        """
        フィルター式を保管する（ポップアップ時）

        @param  expression:式
        """
        self.setFieldFilter(self.column_target, expression)
        self.menu.close()
        self.filterFeatures()


    def setFieldFilter(self, column: int, expression: str):
        """
        フィルター式を保管する

        @param  column:列番号
        @param  expression:式
        """
        self.field_filters[column] = expression
        if self.filter_model is not None:
            # 対象列のヘッダの文字色を赤に変更する
            self.filter_model.setHeaderData(column, Qt.Horizontal, QColor(Qt.red), Qt.ForegroundRole)


    def filterFeatures(self):
        """
        フィルター式を設定する
        """
        if self.layer is None:
            return

        filter_count = len(self.field_filters)
        if filter_count == 0:
            self.showAll()
            return

        filter = " AND ".join(self.field_filters.values())

        filter_expression = QgsExpression(filter)
        if filter_expression.hasParserError():
            # エラーあり
            self.iface.messageBar().pushWarning("Parsing error", filter_expression.parserErrorString())
            return

        context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(self.layer))

        if filter_expression.prepare(context) == False:
            # エラーあり
            self.iface.messageBar().pushWarning("Evaluation error", filter_expression.evalErrorString())
            return

        # フィルター式に設定する
        self.filter_model.setFilterExpression(filter_expression, context)
        self.filter_model.filterFeatures()
        self.setFilterMode(QgsAttributeTableFilterModel.ShowFilteredList)


    def setFilterMode(self, mode: QgsAttributeTableFilterModel.FilterMode):
        """
        フィルターモデルにリクエストとモード設定する

        @param  mode:設定するモード
        """
        if self.filter_model is None:
            return

        # リクエスト初期化
        master_request = QgsFeatureRequest(self.master_model.request())
        # previous request was subset or no features
        requires_table_reload = ((master_request.filterType() != QgsFeatureRequest.FilterNone or master_request.filterRect().isNull() == False) 
                                  or ( self.master_model.rowCount() == 0 ))

        master_request.setFlags(master_request.flags() or QgsFeatureRequest.NoGeometry)
        master_request.setFilterFids( [] )
        master_request.setFilterRect( QgsRectangle() )
        master_request.disableFilter()

        if requires_table_reload:
            self.filter_model.disconnectFilterModeConnections()
            self.master_model.setRequest(master_request)
            self.master_model.loadLayer()

        # モード設定
        self.filter_model.setFilterMode(mode)


    def showAll(self):
        """
        フィルターモデルのモードにShowAllを設定する
        """
        self.setFilterMode(QgsAttributeTableFilterModel.ShowAll)


    def showHeaderContextMenu(self, pos: QPoint):
        """
        メニュー表示

        @param  pos:表示する座標
        """
        if self.filter_model is None:
            return

        # クリックした位置から対象列を特定する
        column_target = self.table_view.horizontalHeader().logicalIndexAt(pos)
        if self.filter_model.actionColumnIndex() == column_target:
            # アクション列なら何もしない
            self.column_target = -1
            return

        self.column_target = column_target

        self.action_option_filter.setText("数値フィルタ" if self.filter_model.layer().fields().at(column_target).isNumeric() else "テキストフィルタ")
        
        # 前回設定したフィルターがあるか確認
        previous_filter = self.field_filters.get(column_target, "")
        # 値フィルターウィジェットアクションにサンプル値を設定する
        QgsApplication.setOverrideCursor(Qt.WaitCursor)
        self.filter_values.setValues(self.column_target, self.filter_model, previous_filter)
        QgsApplication.restoreOverrideCursor()
        # メニューを表示する
        self.menu.popup(self.table_view.horizontalHeader().mapToGlobal(pos))



    def closeEvent(self, event):
        """
        クローズ処理

        @param  event
        """
        self.clear()
        self.closed.emit()
        event.accept()