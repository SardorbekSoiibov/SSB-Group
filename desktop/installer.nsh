!include "nsProcess.nsh"

; Match the application executable exactly. The default path-prefix WMI check
; can mistake a Setup executable in the installation directory for the app.
!macro customCheckAppRunning
  ${nsProcess::FindProcess} "${APP_EXECUTABLE_FILENAME}" $R0
  ${If} $R0 == 0
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "Yangilash uchun SSB Boshqaruv yopiladi. Saqlanmagan ishlaringizni saqlang va OK tugmasini bosing." /SD IDCANCEL IDOK ssb_close_app
    Quit
    ssb_close_app:
    ${nsProcess::CloseProcess} "${APP_EXECUTABLE_FILENAME}" $R0
    Sleep 1500
    ${nsProcess::FindProcess} "${APP_EXECUTABLE_FILENAME}" $R0
    ${If} $R0 == 0
      ${nsProcess::KillProcess} "${APP_EXECUTABLE_FILENAME}" $R0
      Sleep 1000
    ${EndIf}

    ${nsProcess::FindProcess} "${APP_EXECUTABLE_FILENAME}" $R0
    ${If} $R0 == 0
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "SSB Boshqaruv hali ochiq. Ilovani yoping va Qayta urinish tugmasini bosing." /SD IDCANCEL IDRETRY ssb_close_app
      Quit
    ${EndIf}
  ${EndIf}
  ${nsProcess::Unload}
!macroend

