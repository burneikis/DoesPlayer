; DoesPlayer NSIS Installer Script
; Creates a Windows installer with proper uninstall support

;--------------------------------
; Build Configuration (can be overridden via command line)

!ifndef VERSION
    !define VERSION "1.0.0"
!endif

!ifndef APP_NAME
    !define APP_NAME "DoesPlayer"
!endif

!define PUBLISHER "DoesPlayer Team"
!define WEBSITE "https://github.com/doesplayer"
!define APP_EXE "${APP_NAME}.exe"
!define UNINSTALLER "Uninstall.exe"

;--------------------------------
; Includes

!include "MUI2.nsh"
!include "FileFunc.nsh"

;--------------------------------
; General Settings

Name "${APP_NAME}"
OutFile "dist\${APP_NAME}-${VERSION}-Setup.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel admin
Unicode True

; Version info for the installer
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "LegalCopyright" "Copyright ${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"

;--------------------------------
; Interface Settings

!define MUI_ABORTWARNING
;!define MUI_ICON "assets\icon.ico"
;!define MUI_UNICON "assets\icon.ico"

; Welcome page settings
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of ${APP_NAME} ${VERSION}.$\r$\n$\r$\n${APP_NAME} is a high-performance video player with multitrack audio support.$\r$\n$\r$\nClick Next to continue."

; Finish page settings
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_LINK "Visit ${APP_NAME} website"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEBSITE}"

;--------------------------------
; Pages

; Installer pages
!insertmacro MUI_PAGE_WELCOME
;!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Languages

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Section

Section "Install"
    SetOutPath "$INSTDIR"
    
    ; Copy all files from PyInstaller dist folder
    File /r "dist\${APP_NAME}\*.*"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\${UNINSTALLER}"
    
    ; Create Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\${UNINSTALLER}" "" "$INSTDIR\${UNINSTALLER}" 0
    
    ; Create Desktop shortcut (optional)
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    
    ; Write registry keys for uninstaller
    WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\${APP_NAME}" "Version" "${VERSION}"
    
    ; Add/Remove Programs entry
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\${UNINSTALLER}"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "URLInfoAbout" "${WEBSITE}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" 1
    
    ; Calculate and write install size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "EstimatedSize" "$0"
    
    ; Register file associations (optional - for video files)
    ; Uncomment to enable file associations
    ; WriteRegStr HKCR ".mp4\OpenWithProgids" "${APP_NAME}.mp4" ""
    ; WriteRegStr HKCR "${APP_NAME}.mp4" "" "MP4 Video"
    ; WriteRegStr HKCR "${APP_NAME}.mp4\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'
    
SectionEnd

;--------------------------------
; Uninstaller Section

Section "Uninstall"
    ; Remove all installed files
    RMDir /r "$INSTDIR"
    
    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\${APP_NAME}"
    
    ; Remove Desktop shortcut
    Delete "$DESKTOP\${APP_NAME}.lnk"
    
    ; Remove registry keys
    DeleteRegKey HKLM "Software\${APP_NAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    
    ; Remove file associations if they were created
    ; DeleteRegKey HKCR "${APP_NAME}.mp4"
    
SectionEnd

;--------------------------------
; Functions

Function .onInit
    ; Check if already installed, offer to uninstall
    ReadRegStr $0 HKLM "Software\${APP_NAME}" "InstallDir"
    StrCmp $0 "" done
    
    MessageBox MB_YESNO|MB_ICONQUESTION \
        "${APP_NAME} is already installed.$\r$\n$\r$\nDo you want to uninstall the previous version before installing?" \
        IDNO done
    
    ; Run uninstaller silently
    ExecWait '"$0\${UNINSTALLER}" /S _?=$0'
    
done:
FunctionEnd
