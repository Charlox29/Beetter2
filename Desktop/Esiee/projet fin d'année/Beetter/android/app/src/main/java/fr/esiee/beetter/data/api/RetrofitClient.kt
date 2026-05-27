package fr.esiee.beetter.data.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {

    private var _baseUrl: String = ""
    private var _token: String = ""
    private var _api: ApiService? = null

    fun configure(baseUrl: String, token: String) {
        val normalised = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"
        if (normalised != _baseUrl || token != _token) {
            _baseUrl = normalised
            _token = token
            _api = null
        }
    }

    val api: ApiService
        get() {
            if (_api == null) {
                val logging = HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.BODY
                }
                val client = OkHttpClient.Builder()
                    .addInterceptor(logging)
                    .addInterceptor { chain ->
                        val req = chain.request().newBuilder()
                            .addHeader("Authorization", "Bearer $_token")
                            .build()
                        chain.proceed(req)
                    }
                    .build()

                _api = Retrofit.Builder()
                    .baseUrl(_baseUrl)
                    .client(client)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build()
                    .create(ApiService::class.java)
            }
            return _api!!
        }
}
