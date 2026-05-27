package fr.esiee.beetter.data.model

import com.google.gson.annotations.SerializedName

// ── Auth ──────────────────────────────────────────────────────────────────────

data class LoginRequest(
    val username: String,
    val password: String,
)

data class LoginResponse(
    val token: String,
    val username: String,
    @SerializedName("expires_at") val expiresAt: String,
)

// ── Beehive list ──────────────────────────────────────────────────────────────

data class SensorValue(
    val value: Double?,
    val time: String?,
)

data class BeehiveLatest(
    val temperature: SensorValue?,
    val humidity: SensorValue?,
)

data class BeehiveItem(
    val id: String,
    val latest: BeehiveLatest?,
)

data class BeehivesResponse(
    val beehives: List<BeehiveItem>,
)

// ── Chart data ────────────────────────────────────────────────────────────────

data class ChartSeries(
    val labels: List<String>,
    val data: List<Double?>,
)

data class ChartDataResponse(
    val temperature: ChartSeries?,
    val humidity: ChartSeries?,
)
