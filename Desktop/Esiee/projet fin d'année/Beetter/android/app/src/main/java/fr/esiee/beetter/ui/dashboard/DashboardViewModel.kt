package fr.esiee.beetter.ui.dashboard

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.esiee.beetter.data.api.RetrofitClient
import fr.esiee.beetter.data.model.BeehiveItem
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.data.repository.BeehiveRepository
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class DashboardUiState(
    val beehives: List<BeehiveItem> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

class DashboardViewModel(app: Application) : AndroidViewModel(app) {

    private val prefs = UserPreferences(app)
    private val repo  = BeehiveRepository()

    private val _state = MutableStateFlow(DashboardUiState(isLoading = true))
    val state: StateFlow<DashboardUiState> = _state

    val username = prefs.username

    init {
        viewModelScope.launch {
            val url   = prefs.serverUrl.first() ?: return@launch
            val token = prefs.authToken.first()  ?: return@launch
            RetrofitClient.configure(url, token)
            load()
        }
    }

    fun refresh() {
        viewModelScope.launch { load() }
    }

    private suspend fun load() {
        _state.update { it.copy(isLoading = true, error = null) }
        try {
            val response = repo.getBeehives()
            _state.update { it.copy(beehives = response.beehives, isLoading = false) }
        } catch (e: Exception) {
            _state.update { it.copy(isLoading = false, error = e.message ?: "Failed to load.") }
        }
    }
}
