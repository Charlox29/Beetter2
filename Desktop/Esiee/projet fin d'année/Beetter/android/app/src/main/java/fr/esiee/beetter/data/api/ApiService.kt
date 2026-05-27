package fr.esiee.beetter.data.api

import fr.esiee.beetter.data.model.*
import retrofit2.http.*

interface ApiService {

    @POST("api/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @POST("api/auth/logout")
    suspend fun logout()

    @GET("api/beehives")
    suspend fun getBeehives(): BeehivesResponse

    @GET("api/beehives/{id}/data")
    suspend fun getBeehiveData(
        @Path("id") id: String,
        @Query("range") range: String = "24h",
    ): ChartDataResponse
}
