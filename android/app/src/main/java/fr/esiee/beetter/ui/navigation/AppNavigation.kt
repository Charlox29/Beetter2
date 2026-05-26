package fr.esiee.beetter.ui.navigation

import androidx.compose.runtime.*
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import fr.esiee.beetter.data.prefs.UserPreferences
import fr.esiee.beetter.data.api.RetrofitClient
import fr.esiee.beetter.ui.login.LoginScreen
import fr.esiee.beetter.ui.dashboard.DashboardScreen
import fr.esiee.beetter.ui.detail.BeehiveDetailScreen
import fr.esiee.beetter.ui.settings.SettingsScreen
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

@Composable
fun AppNavigation(prefs: UserPreferences) {
    val navController = rememberNavController()

    // Determine start destination synchronously at composition time
    val startDest = remember {
        val token = runBlocking { prefs.authToken.first() }
        val url   = runBlocking { prefs.serverUrl.first() }
        if (!token.isNullOrEmpty() && !url.isNullOrEmpty()) {
            RetrofitClient.configure(url, token)
            "dashboard"
        } else {
            "login"
        }
    }

    NavHost(navController = navController, startDestination = startDest) {
        composable("login") {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate("dashboard") {
                        popUpTo("login") { inclusive = true }
                    }
                }
            )
        }
        composable("dashboard") {
            DashboardScreen(
                onBeehiveClick = { id -> navController.navigate("beehive/$id") },
                onSettingsClick = { navController.navigate("settings") },
            )
        }
        composable("beehive/{beehiveId}") { back ->
            val id = back.arguments?.getString("beehiveId") ?: return@composable
            BeehiveDetailScreen(
                beehiveId = id,
                onBack = { navController.popBackStack() },
            )
        }
        composable("settings") {
            SettingsScreen(
                onLogout = {
                    navController.navigate("login") {
                        popUpTo(0) { inclusive = true }
                    }
                },
                onBack = { navController.popBackStack() },
            )
        }
    }
}
