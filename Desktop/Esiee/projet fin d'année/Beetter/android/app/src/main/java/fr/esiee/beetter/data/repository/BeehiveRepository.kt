package fr.esiee.beetter.data.repository

import fr.esiee.beetter.data.api.RetrofitClient
import fr.esiee.beetter.data.model.*

class BeehiveRepository {

    suspend fun login(serverUrl: String, username: String, password: String): LoginResponse {
        RetrofitClient.configure(serverUrl, "")
        return RetrofitClient.api.login(LoginRequest(username, password))
    }

    suspend fun logout() = runCatching { RetrofitClient.api.logout() }

    suspend fun getBeehives(): BeehivesResponse = RetrofitClient.api.getBeehives()

    suspend fun getBeehiveData(id: String, range: String): ChartDataResponse =
        RetrofitClient.api.getBeehiveData(id, range)
}
