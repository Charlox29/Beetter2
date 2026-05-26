package fr.esiee.beetter.data.prefs

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "beetter_prefs")

class UserPreferences(private val context: Context) {

    companion object {
        val SERVER_URL         = stringPreferencesKey("server_url")
        val AUTH_TOKEN         = stringPreferencesKey("auth_token")
        val USERNAME           = stringPreferencesKey("username")
        val NOTIFICATIONS_ON   = booleanPreferencesKey("notifications_enabled")
        val TEMP_MAX           = floatPreferencesKey("temp_max")
        val TEMP_MIN           = floatPreferencesKey("temp_min")
        val HUM_MAX            = floatPreferencesKey("hum_max")
        val HUM_MIN            = floatPreferencesKey("hum_min")
    }

    val serverUrl: Flow<String?>  = context.dataStore.data.map { it[SERVER_URL] }
    val authToken: Flow<String?>  = context.dataStore.data.map { it[AUTH_TOKEN] }
    val username:  Flow<String?>  = context.dataStore.data.map { it[USERNAME] }
    val notificationsEnabled: Flow<Boolean> = context.dataStore.data.map { it[NOTIFICATIONS_ON] ?: false }
    val tempMax: Flow<Float> = context.dataStore.data.map { it[TEMP_MAX] ?: 40f }
    val tempMin: Flow<Float> = context.dataStore.data.map { it[TEMP_MIN] ?: 5f }
    val humMax:  Flow<Float> = context.dataStore.data.map { it[HUM_MAX]  ?: 90f }
    val humMin:  Flow<Float> = context.dataStore.data.map { it[HUM_MIN]  ?: 20f }

    suspend fun saveSession(serverUrl: String, token: String, username: String) {
        context.dataStore.edit { prefs ->
            prefs[SERVER_URL]  = serverUrl
            prefs[AUTH_TOKEN]  = token
            prefs[USERNAME]    = username
        }
    }

    suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(AUTH_TOKEN)
            prefs.remove(USERNAME)
        }
    }

    suspend fun saveNotificationSettings(
        enabled: Boolean,
        tempMax: Float,
        tempMin: Float,
        humMax: Float,
        humMin: Float,
    ) {
        context.dataStore.edit { prefs ->
            prefs[NOTIFICATIONS_ON] = enabled
            prefs[TEMP_MAX] = tempMax
            prefs[TEMP_MIN] = tempMin
            prefs[HUM_MAX]  = humMax
            prefs[HUM_MIN]  = humMin
        }
    }
}
