package fr.esiee.beetter.ui.detail

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import fr.esiee.beetter.data.model.ChartDataResponse
import fr.esiee.beetter.data.repository.BeehiveRepository
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class DetailUiState(
    val data: ChartDataResponse? = null,
    val range: String = "24h",
    val isLoading: Boolean = false,
    val error: String? = null,
)

val RANGES = listOf("1h", "6h", "24h", "7d", "30d")

class BeehiveDetailViewModel(app: Application) : AndroidViewModel(app) {

    private val repo = BeehiveRepository()

    private val _state = MutableStateFlow(DetailUiState(isLoading = true))
    val state: StateFlow<DetailUiState> = _state

    fun load(beehiveId: String, range: String = _state.value.range) {
        _state.update { it.copy(isLoading = true, error = null, range = range) }
        viewModelScope.launch {
            try {
                val data = repo.getBeehiveData(beehiveId, range)
                _state.update { it.copy(data = data, isLoading = false) }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = e.message ?: "Failed to load data.") }
            }
        }
    }
}
