package fr.esiee.beetter.worker

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.work.*
import fr.esiee.beetter.data.api.RetrofitClient
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.data.repository.BeehiveRepository
import kotlinx.coroutines.flow.first
import java.util.concurrent.TimeUnit

class AlertWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        private const val CHANNEL_ID  = "beetter_alerts"
        private const val WORK_NAME   = "beetter_alert_check"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }

    override suspend fun doWork(): Result {
        val prefs = UserPreferences(applicationContext)

        if (!prefs.notificationsEnabled.first()) return Result.success()

        val serverUrl = prefs.serverUrl.first() ?: return Result.success()
        val token     = prefs.authToken.first()  ?: return Result.success()
        val tempMax   = prefs.tempMax.first()
        val tempMin   = prefs.tempMin.first()
        val humMax    = prefs.humMax.first()
        val humMin    = prefs.humMin.first()

        RetrofitClient.configure(serverUrl, token)
        val beehives = try {
            BeehiveRepository().getBeehives().beehives
        } catch (e: Exception) {
            return Result.retry()
        }

        ensureNotificationChannel()

        beehives.forEach { hive ->
            val temp = hive.latest?.temperature?.value
            val hum  = hive.latest?.humidity?.value

            if (temp != null && temp > tempMax)
                notify("Beehive #${hive.id} — high temperature", "%.1f°C (max %.1f°C)".format(temp, tempMax))
            if (temp != null && temp < tempMin)
                notify("Beehive #${hive.id} — low temperature", "%.1f°C (min %.1f°C)".format(temp, tempMin))
            if (hum != null && hum > humMax)
                notify("Beehive #${hive.id} — high humidity", "%.1f%% (max %.1f%%)".format(hum, humMax))
            if (hum != null && hum < humMin)
                notify("Beehive #${hive.id} — low humidity", "%.1f%% (min %.1f%%)".format(hum, humMin))
        }

        return Result.success()
    }

    private fun ensureNotificationChannel() {
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Beehive alerts", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }

    private fun notify(title: String, body: String) {
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .build()
        nm.notify(System.currentTimeMillis().toInt(), notification)
    }
}
