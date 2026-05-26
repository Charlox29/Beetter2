package fr.esiee.beetter

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.ui.navigation.AppNavigation
import fr.esiee.beetter.ui.theme.BeeterTheme
import fr.esiee.beetter.worker.AlertWorker

class MainActivity : ComponentActivity() {

    private val requestNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) AlertWorker.schedule(this)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        requestNotificationPermissionIfNeeded()

        val prefs = UserPreferences(applicationContext)

        setContent {
            BeeterTheme {
                AppNavigation(prefs = prefs)
            }
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            when {
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        == PackageManager.PERMISSION_GRANTED -> AlertWorker.schedule(this)
                else -> requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        } else {
            AlertWorker.schedule(this)
        }
    }
}
