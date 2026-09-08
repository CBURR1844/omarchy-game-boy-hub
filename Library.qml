import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "bam1844.game-boy"
  ipcTarget: moduleName
  manageIpc: false
  implicitWidth: barButton.implicitWidth
  implicitHeight: barButton.implicitHeight
  readonly property string helper: Qt.resolvedUrl("hub.py").toString().replace("file://", "")
  property var libraryData: ({games: [], warnings: [], settings: {speed: 4, rewind: true, fullscreen: false, folders: []}, installed: false})
  property string message: ""
  property string query: ""
  property string filter: "All"
  property string tab: "Library"
  property string selectedPath: ""
  property string pendingPatchPath: ""
  property string action: ""
  property var cheatResult: ({rom: "", title: "", identity: "", notice: "", candidates: [], entries: [], sourceId: ""})
  property var chosenCheats: []
  property string cheatQuery: ""
  readonly property var filteredCheats: cheatResult.entries.filter(function(e) { return !cheatQuery || e.name.toLowerCase().indexOf(cheatQuery.toLowerCase()) >= 0 })
  readonly property bool busy: worker.running
  readonly property var filteredGames: {
    var needle = query.toLowerCase().trim()
    var items = libraryData.games.filter(function(g) {
      return (!needle || (g.title + " " + g.system).toLowerCase().indexOf(needle) >= 0)
          && (filter !== "Favorites" || g.favorite) && (filter !== "Recent" || g.recent >= 0)
    })
    if (filter === "Recent") items.sort(function(a, b) { return a.recent - b.recent })
    return items
  }
  readonly property var selectedGame: {
    for (var i = 0; i < libraryData.games.length; i++) if (libraryData.games[i].path === selectedPath) return libraryData.games[i]
    return null
  }
  function run(args) {
    if (busy) return
    message = ""
    action = args[0]
    worker.command = ["/usr/bin/python3", decodeURIComponent(helper)].concat(args)
    worker.running = true
  }
  function refresh() { run(["scan"]) }
  function play(path) { if (path) run(["launch", path]) }
  function localPath(url) { return decodeURIComponent(url.toString().replace(/^file:\/\//, "")) }
  function setOption(key, value) { run(["setting", key, String(value)]) }
  function findCheats() {
    if (!selectedPath || busy) return
    tab = "Cheats"
    chosenCheats = []
    cheatQuery = ""
    run(["cheats-find", selectedPath])
  }
  function chooseCheat(id) {
    chosenCheats = chosenCheats.indexOf(id) >= 0 ? chosenCheats.filter(function(v) { return v !== id }) : chosenCheats.concat([id])
  }
  onOpenedChanged: if (opened) refresh()
  onFilteredGamesChanged: {
    var found = filteredGames.some(function(g) { return g.path === selectedPath })
    if (!found) selectedPath = filteredGames.length ? filteredGames[0].path : ""
  }
  Process {
    id: worker
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (result.error) root.message = result.error
          else if (result.cheatResult) { root.cheatResult = result.cheatResult; root.chosenCheats = []; root.cheatQuery = "" }
          else if (result.cheatMessage) root.message = result.cheatMessage
          else if (result.games !== undefined) root.libraryData = result
          else if (result.ok && root.action === "launch") root.close()
        } catch (e) { root.message = "Could not read the library response." }
      }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text.trim()) console.warn("game-boy-hub", text.trim())
    }
  }
  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function findCheats(): void { root.findCheats() }
    function status(): string { return JSON.stringify({games: root.libraryData.games.length, installed: root.libraryData.installed, error: root.message, open: root.opened, tab: root.tab, cheatLists: root.cheatResult.candidates.length, cheatCodes: root.cheatResult.entries.length}) }
  }
  FileDialog {
    id: romPicker
    title: "Open a Game Boy ROM"
    nameFilters: ["Game Boy ROMs (*.gba *.gb *.gbc *.zip *.7z)"]
    onAccepted: root.play(root.localPath(selectedFile))
  }
  FolderDialog {
    id: folderPicker
    title: "Add a ROM folder"
    onAccepted: root.run(["add-folder", root.localPath(selectedFolder)])
  }
  FileDialog {
    id: patchPicker
    title: "Choose an IPS, UPS or BPS ROM hack"
    nameFilters: ["ROM patches (*.ips *.ups *.bps)"]
    onAccepted: root.run(["patch", root.pendingPatchPath, root.localPath(selectedFile)])
  }
  BarIconButton {
    id: barButton
    anchors.fill: parent
    bar: root.bar
    text: "󰊖"
    onPressed: function(button) {
      if (button === Qt.RightButton) root.run(["launch"])
      else root.toggle()
    }
  }
  KeyboardPanel {
    id: popup
    anchorItem: barButton
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: search
    contentWidth: fittedContentWidth(Style.space(490))
    contentHeight: cappedContentHeight(Style.space(645))

    FocusScope {
      anchors.fill: parent
      Keys.onEscapePressed: root.close()
      ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(12)
        RowLayout {
          Layout.fillWidth: true
          ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space(3)
            Text { text: "GAME BOY HUB"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
            Text { text: "GB · GBC · GBA  /  " + root.libraryData.games.length + " games"; color: Color.foreground; opacity: 0.65; font.family: Style.font.family; font.pixelSize: Style.font.body }
          }
          HubButton { text: "×"; implicitWidth: Style.space(32); onClicked: root.close() }
        }
        RowLayout {
          Layout.fillWidth: true
          Repeater {
            model: ["Library", "Cheats", "Setup", "Controls"]
            HubButton { required property string modelData; Layout.fillWidth: true; text: modelData; selected: root.tab === modelData; onClicked: { if (modelData === "Cheats" && root.cheatResult.rom !== root.selectedPath) root.findCheats(); else root.tab = modelData } }
          }
        }
        Text {
          Layout.fillWidth: true
          visible: root.message !== "" || root.busy || (!root.libraryData.installed && root.libraryData.games.length > 0)
          text: root.message || (root.busy ? "Working…" : "mGBA is not installed.")
          wrapMode: Text.Wrap
          color: root.message ? Color.urgent : Color.foreground
          font.family: Style.font.family; font.pixelSize: Style.font.body
        }

        ColumnLayout {
          visible: root.tab === "Library"
          Layout.fillWidth: true; Layout.fillHeight: true
          spacing: Style.space(10)
          Controls.TextField {
            id: search
            Layout.fillWidth: true
            placeholderText: "Search your games…"
            text: root.query
            onTextEdited: root.query = text
            color: Color.foreground
            placeholderTextColor: Qt.alpha(Color.foreground, 0.5)
            selectionColor: Color.accent
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            leftPadding: Style.space(10)
            implicitHeight: Style.space(38)
            background: Rectangle { color: Qt.alpha(Color.foreground, 0.04); radius: Style.cornerRadius; border.width: 1; border.color: search.activeFocus ? Color.accent : Qt.alpha(Color.foreground, 0.2) }
            Keys.onEscapePressed: root.close()
            Keys.onDownPressed: { games.currentIndex = 0; games.forceActiveFocus() }
            onAccepted: root.play(root.selectedPath)
          }
          RowLayout {
            Repeater {
              model: ["All", "Favorites", "Recent"]
              HubButton { required property string modelData; text: modelData; selected: root.filter === modelData; onClicked: root.filter = modelData }
            }
            Item { Layout.fillWidth: true }
            HubButton { text: "↻"; enabled: !root.busy; onClicked: root.refresh() }
          }
          ListView {
            id: games
            Layout.fillWidth: true; Layout.fillHeight: true
            model: root.filteredGames
            clip: true
            spacing: Style.space(5)
            boundsBehavior: Flickable.StopAtBounds
            Controls.ScrollBar.vertical: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
            Keys.onReturnPressed: root.play(root.selectedPath)
            Keys.onEnterPressed: root.play(root.selectedPath)
            Keys.onEscapePressed: root.close()
            onCurrentIndexChanged: if (currentIndex >= 0 && currentIndex < root.filteredGames.length) root.selectedPath = root.filteredGames[currentIndex].path
            delegate: Rectangle {
              required property var modelData
              required property int index
              width: games.width
              height: Style.space(64)
              radius: Style.cornerRadius
              color: root.selectedPath === modelData.path ? Style.selectedFillFor(Color.foreground, Color.accent)
                    : rowMouse.containsMouse ? Style.hoverFillFor(Color.foreground, Color.accent) : "transparent"
              border.width: root.selectedPath === modelData.path ? 1 : 0
              border.color: Qt.alpha(Color.accent, 0.65)
              MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { root.selectedPath = modelData.path; games.currentIndex = index }
                onDoubleClicked: root.play(modelData.path)
              }
              Column {
                anchors.left: parent.left; anchors.right: favorite.left
                anchors.leftMargin: Style.space(12); anchors.rightMargin: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(4)
                Text { width: parent.width; text: modelData.title; elide: Text.ElideRight; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                Text { width: parent.width; text: modelData.system + (modelData.patch ? " · ROM hack attached" : "") + (modelData.recent === 0 ? " · Last played" : ""); elide: Text.ElideRight; color: Color.foreground; opacity: 0.6; font.family: Style.font.family; font.pixelSize: Style.font.body }
              }
              HubButton {
                id: favorite
                anchors.right: parent.right; anchors.rightMargin: Style.space(6); anchors.verticalCenter: parent.verticalCenter
                text: modelData.favorite ? "★" : "☆"
                implicitWidth: Style.space(34)
                enabled: !root.busy
                onClicked: root.run(["favorite", modelData.path])
              }
            }
            Text {
              anchors.centerIn: parent
              width: parent.width - Style.space(28)
              visible: games.count === 0
              text: root.libraryData.games.length ? "No matching games." : "Your next adventure starts here.\nAdd a ROM folder below."
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.Wrap
              color: Color.foreground; opacity: 0.65
              font.family: Style.font.family; font.pixelSize: Style.font.body
            }
          }
          Text {
            Layout.fillWidth: true
            visible: root.selectedGame && root.selectedGame.patch !== ""
            text: root.selectedGame ? "Patch: " + root.selectedGame.patch.split("/").pop() : ""
            elide: Text.ElideMiddle
            color: Color.accent; font.family: Style.font.family; font.pixelSize: Style.font.body
          }
          RowLayout {
            Layout.fillWidth: true
            HubButton { text: "▶  Play"; selected: true; Layout.fillWidth: true; enabled: !!root.selectedGame && root.libraryData.installed && !root.busy; onClicked: root.play(root.selectedPath) }
            HubButton { text: "Find cheats"; enabled: !!root.selectedGame && !root.busy; onClicked: root.findCheats() }
            HubButton { text: "Patch…"; enabled: !!root.selectedGame && !root.busy; onClicked: { root.pendingPatchPath = root.selectedPath; patchPicker.open() } }
            HubButton { text: "Clear"; visible: !!root.selectedGame && root.selectedGame.patch !== ""; enabled: !root.busy; onClicked: root.run(["patch", root.selectedPath]) }
          }
          RowLayout {
            Layout.fillWidth: true
            HubButton { text: "Add folder…"; Layout.fillWidth: true; enabled: !root.busy; onClicked: folderPicker.open() }
            HubButton { text: "Open ROM…"; Layout.fillWidth: true; enabled: !root.busy; onClicked: romPicker.open() }
          }
        }

        ColumnLayout {
          visible: root.tab === "Cheats"
          Layout.fillWidth: true; Layout.fillHeight: true
          spacing: Style.space(9)
          Text { Layout.fillWidth: true; text: root.cheatResult.title || "Select a game in Library"; elide: Text.ElideRight; color: Color.foreground; font.bold: true; font.family: Style.font.family; font.pixelSize: Style.font.body }
          Text { Layout.fillWidth: true; visible: root.cheatResult.identity !== ""; text: root.cheatResult.identity; wrapMode: Text.Wrap; color: Color.accent; font.family: Style.font.family; font.pixelSize: Style.font.body }
          Text { Layout.fillWidth: true; text: root.cheatResult.notice; wrapMode: Text.Wrap; color: Color.foreground; opacity: 0.75; font.family: Style.font.family; font.pixelSize: Style.font.body }
          RowLayout {
            HubButton { text: "Find again"; enabled: !root.busy && !!root.selectedGame; onClicked: root.findCheats() }
            HubButton { text: "Back to lists"; visible: root.cheatResult.sourceId !== ""; enabled: !root.busy; onClicked: { var result = Object.assign({}, root.cheatResult); result.sourceId = ""; result.entries = []; root.cheatResult = result; root.chosenCheats = [] } }
          }
          ListView {
            visible: root.cheatResult.sourceId === ""
            Layout.fillWidth: true; Layout.fillHeight: true
            model: root.cheatResult.candidates
            clip: true; spacing: Style.space(6)
            Controls.ScrollBar.vertical: Controls.ScrollBar {}
            delegate: HubButton {
              required property var modelData
              width: ListView.view.width
              implicitHeight: Style.space(72)
              enabled: !root.busy
              contentItem: Column {
                spacing: Style.space(3)
                Text { width: parent.width; text: modelData.name; wrapMode: Text.Wrap; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                Text { width: parent.width; text: modelData.match; elide: Text.ElideRight; color: Color.foreground; opacity: 0.6; font.family: Style.font.family; font.pixelSize: Style.font.body }
              }
              onClicked: root.run(["cheats-preview", root.cheatResult.rom, modelData.id])
            }
          }
          Controls.TextField {
            visible: root.cheatResult.sourceId !== ""
            Layout.fillWidth: true
            placeholderText: "Search codes: money, balls, experience…"
            text: root.cheatQuery
            onTextEdited: root.cheatQuery = text
            color: Color.foreground; placeholderTextColor: Qt.alpha(Color.foreground, 0.5)
            font.family: Style.font.family; font.pixelSize: Style.font.body
            implicitHeight: Style.space(36); leftPadding: Style.space(8)
            background: Rectangle { color: "transparent"; border.width: 1; border.color: Color.accent }
          }
          ListView {
            visible: root.cheatResult.sourceId !== ""
            Layout.fillWidth: true; Layout.fillHeight: true
            model: root.filteredCheats
            clip: true; spacing: Style.space(4)
            Controls.ScrollBar.vertical: Controls.ScrollBar {}
            delegate: HubButton {
              required property var modelData
              width: ListView.view.width
              text: (root.chosenCheats.indexOf(modelData.id) >= 0 ? "✓  " : "+  ") + modelData.name
              selected: root.chosenCheats.indexOf(modelData.id) >= 0
              enabled: !root.busy
              onClicked: root.chooseCheat(modelData.id)
            }
          }
          HubButton {
            visible: root.cheatResult.sourceId !== ""
            Layout.fillWidth: true
            text: "Import selected (" + root.chosenCheats.length + ")"
            selected: true
            enabled: !root.busy && root.chosenCheats.length > 0 && root.chosenCheats.length <= 1000
            onClicked: root.run(["cheats-import", root.cheatResult.rom, root.cheatResult.sourceId, root.chosenCheats.join(",")])
          }
          Text { Layout.fillWidth: true; text: "Database: Libretro · Identification: No-Intro\nEnable imported codes in mGBA → Tools → Cheats."; wrapMode: Text.Wrap; color: Color.foreground; opacity: 0.6; font.family: Style.font.family; font.pixelSize: Style.font.body }
        }

        Flickable {
          visible: root.tab === "Setup"
          Layout.fillWidth: true; Layout.fillHeight: true
          contentHeight: settingsColumn.implicitHeight
          clip: true
          boundsBehavior: Flickable.StopAtBounds
          Controls.ScrollBar.vertical: Controls.ScrollBar {}
          ColumnLayout {
            id: settingsColumn
            width: parent.width
            spacing: Style.space(14)
            Text { text: "FAST-FORWARD SPEED"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
            RowLayout {
              Repeater {
                model: [{label:"2×",value:2},{label:"4×",value:4},{label:"8×",value:8},{label:"Unlimited",value:-1}]
                HubButton { required property var modelData; text: modelData.label; selected: root.libraryData.settings.speed === modelData.value; enabled: !root.busy; onClicked: root.setOption("speed", modelData.value) }
              }
            }
            Text { Layout.fillWidth: true; text: "Hold Tab to speed up. Shift+Tab toggles it.\nPresets apply when you launch a game; change a running game's speed in Emulation → Fast forward speed."; wrapMode: Text.Wrap; color: Color.foreground; opacity: 0.7; font.family: Style.font.family; font.pixelSize: Style.font.body }
            HubButton { text: "Rewind: " + (root.libraryData.settings.rewind ? "On" : "Off"); selected: root.libraryData.settings.rewind; enabled: !root.busy; onClicked: root.setOption("rewind", !root.libraryData.settings.rewind) }
            HubButton { text: "Start fullscreen: " + (root.libraryData.settings.fullscreen ? "On" : "Off"); selected: root.libraryData.settings.fullscreen; enabled: !root.busy; onClicked: root.setOption("fullscreen", !root.libraryData.settings.fullscreen) }
            Text { text: "YOUR FILES"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
            RowLayout {
              HubButton { text: "ROMs"; enabled: !root.busy; onClicked: root.run(["folder", "roms"]) }
              HubButton { text: "Saves"; enabled: !root.busy; onClicked: root.run(["folder", "saves"]) }
              HubButton { text: "Screenshots"; enabled: !root.busy; onClicked: root.run(["folder", "screenshots"]) }
            }
            Text { Layout.fillWidth: true; text: "Saves and cheats stay in a separate folder for each game. Patched games get their own saves. Your original ROM stays unchanged."; wrapMode: Text.Wrap; color: Color.foreground; opacity: 0.7; font.family: Style.font.family; font.pixelSize: Style.font.body }
            Repeater {
              model: root.libraryData.settings.folders
              RowLayout {
                required property string modelData
                Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: modelData; elide: Text.ElideMiddle; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                HubButton { text: "Remove"; enabled: !root.busy; onClicked: root.run(["remove-folder", modelData]) }
              }
            }
            Text { Layout.fillWidth: true; text: "Removing a folder only removes it from the library."; wrapMode: Text.Wrap; color: Color.foreground; opacity: 0.6; font.family: Style.font.family; font.pixelSize: Style.font.body }
            Text { Layout.fillWidth: true; text: root.libraryData.warnings.join("\n"); visible: text !== ""; wrapMode: Text.Wrap; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.body }
          }
        }

        Flickable {
          visible: root.tab === "Controls"
          Layout.fillWidth: true; Layout.fillHeight: true
          contentHeight: help.implicitHeight
          clip: true
          Controls.ScrollBar.vertical: Controls.ScrollBar {}
          Text {
            id: help
            width: parent.width
            textFormat: Text.RichText
            wrapMode: Text.Wrap
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            text: "<b>PLAY</b><br>Arrow keys — Move<br>X / Z — A / B<br>A / S — L / R<br>Enter — Start · Backspace — Select<br><br><b>TIME &amp; SAVES</b><br>Tab — Hold fast-forward<br>Shift+Tab — Toggle fast-forward<br>` (backtick) — Hold rewind<br>Ctrl+P — Pause<br>Shift+F1…F9 — Save state<br>F1…F9 — Load state<br><br><b>CHEATS &amp; ROM HACKS</b><br>In the game, open Tools → Cheats to add codes. Codes must match your game and version. For an IPS, UPS or BPS patch, select a game here, choose ROM hack…, then Play. The patch must match the original ROM revision.<br><br><b>CONTROLLERS &amp; EXTRAS</b><br>Tools → Settings provides keyboard and controller mapping, shortcuts, video and audio options. The menus also provide screenshots, recording and local multiplayer windows.<br><br>Game compatibility and maximum fast-forward speed depend on the ROM and your hardware. Rewind has a finite history and is unavailable in multiplayer."
          }
        }
      }
    }
  }
}
