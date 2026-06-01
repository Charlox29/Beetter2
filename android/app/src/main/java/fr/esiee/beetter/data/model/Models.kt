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

/**
 * Latest known value for each sensor stream of a beehive.
 * Keys map to the InfluxDB measurement names produced by the Raspberry Pi.
 */
data class BeehiveLatest(
    @SerializedName("temperature_int") val temperatureInt: SensorValue?,
    @SerializedName("humidity_int")    val humidityInt: SensorValue?,
    @SerializedName("temperature_ext") val temperatureExt: SensorValue?,
    @SerializedName("humidity_ext")    val humidityExt: SensorValue?,
    @SerializedName("sound_freq_int")  val soundFreqInt: SensorValue?,
    @SerializedName("sound_amp_int")   val soundAmpInt: SensorValue?,
    @SerializedName("sound_freq_ext")  val soundFreqExt: SensorValue?,
    @SerializedName("sound_amp_ext")   val soundAmpExt: SensorValue?,
    @SerializedName("light_ext")       val lightExt: SensorValue?,
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
    @SerializedName("temperature_int") val temperatureInt: ChartSeries?,
    @SerializedName("humidity_int")    val humidityInt: ChartSeries?,
    @SerializedName("temperature_ext") val temperatureExt: ChartSeries?,
    @SerializedName("humidity_ext")    val humidityExt: ChartSeries?,
    @SerializedName("sound_freq_int")  val soundFreqInt: ChartSeries?,
    @SerializedName("sound_amp_int")   val soundAmpInt: ChartSeries?,
    @SerializedName("sound_freq_ext")  val soundFreqExt: ChartSeries?,
    @SerializedName("sound_amp_ext")   val soundAmpExt: ChartSeries?,
    @SerializedName("light_ext")       val lightExt: ChartSeries?,
)
