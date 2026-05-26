package fr.esiee.beetter.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.data.repository.BeehiveRepository
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class SettingsViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = UserPreferences(app)
    private val repo  = BeehiveRepository()

    val username          = prefs.username
    val serverUrl         = prefs.serverUrl
    val notificationsEnabled = prefs.notificationsEnabled
    val tempMax           = prefs.tempMax
    val tempMin           = prefs.tempMin
    val humMax            = prefs.humMax
    val humMin            = prefs.humMin

    private val _loggedOut = MutableStateFlow(false)
    val loggedOut: StateFlow<Boolean> = _loggedOut

    fun saveNotifications(enabled: Boolean, tMax: Float, tMin: Float, hMax: Float, hMin: Float) {
        viewModelScope.launch {
            prefs.saveNotificationSettings(enabled, tMax, tMin, hMax, hMin)
        }
    }

    fun logout() {
        viewModelScope.launch {
            repo.logout()
            prefs.clearSession()
            _loggedOut.value = true
        }
    }
}
