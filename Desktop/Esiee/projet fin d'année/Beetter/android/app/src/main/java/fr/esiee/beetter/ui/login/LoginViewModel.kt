package fr.esiee.beetter.ui.login

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.esiee.beetter.data.api.RetrofitClient
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.data.repository.BeehiveRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

sealed class LoginState {
    object Idle : LoginState()
    object Loading : LoginState()
    object Success : LoginState()
    data class Error(val message: String) : LoginState()
}

class LoginViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = UserPreferences(app)
    private val repo  = BeehiveRepository()

    private val _state = MutableStateFlow<LoginState>(LoginState.Idle)
    val state: StateFlow<LoginState> = _state

    // Pre-fill the URL field if a server was previously configured
    val savedServerUrl = prefs.serverUrl

    fun login(serverUrl: String, username: String, password: String) {
        if (serverUrl.isBlank() || username.isBlank() || password.isBlank()) {
            _state.value = LoginState.Error("All fields are required.")
            return
        }
        _state.value = LoginState.Loading
        viewModelScope.launch {
            try {
                val response = repo.login(serverUrl.trim(), username.trim(), password)
                prefs.saveSession(serverUrl.trim(), response.token, response.username)
                RetrofitClient.configure(serverUrl.trim(), response.token)
                _state.value = LoginState.Success
            } catch (e: Exception) {
                _state.value = LoginState.Error(e.message ?: "Login failed.")
            }
        }
    }
}
