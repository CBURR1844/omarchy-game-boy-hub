import QtQuick
import QtQuick.Controls as Controls
import qs.Commons

Controls.Button {
  id: root
  property bool selected: false
  implicitHeight: Style.space(34)
  implicitWidth: label.implicitWidth + Style.space(22)
  opacity: enabled ? 1 : 0.4
  contentItem: Text {
    id: label
    text: root.text
    font.family: Style.font.family
    font.pixelSize: Style.font.body
    color: Color.foreground
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
  }
  background: Rectangle {
    radius: Style.cornerRadius
    color: root.selected ? Style.selectedFillFor(Color.foreground, Color.accent)
                        : root.hovered ? Style.hoverFillFor(Color.foreground, Color.accent) : "transparent"
    border.width: 1
    border.color: root.selected || root.activeFocus ? Color.accent : Qt.alpha(Color.foreground, 0.22)
  }
}
