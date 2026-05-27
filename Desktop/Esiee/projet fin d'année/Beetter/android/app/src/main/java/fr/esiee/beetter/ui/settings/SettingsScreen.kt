package fr.esiee.beetter.ui.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onLogout: () -> Unit,
    onBack: () -> Unit,
    vm: SettingsViewModel = viewModel(),
) {
    val loggedOut       by vm.loggedOut.collectAsState()
    val username        by vm.username.collectAsState(initial = "")
    val serverUrl       by vm.serverUrl.collectAsState(initial = "")
    val notifEnabled    by vm.notificationsEnabled.collectAsState(initial = false)
    val savedTempMax    by vm.tempMax.collectAsState(initial = 40f)
    val savedTempMin    by vm.tempMin.collectAsState(initial = 5f)
    val savedHumMax     by vm.humMax.collectAsState(initial = 90f)
    val savedHumMin     by vm.humMin.collectAsState(initial = 20f)

    var notifOn  by remember(notifEnabled) { mutableStateOf(notifEnabled) }
    var tMax     by remember(savedTempMax) { mutableStateOf(savedTempMax.toString()) }
    var tMin     by remember(savedTempMin) { mutableStateOf(savedTempMin.toString()) }
    var hMax     by remember(savedHumMax)  { mutableStateOf(savedHumMax.toString()) }
    var hMin     by remember(savedHumMin)  { mutableStateOf(savedHumMin.toString()) }

    LaunchedEffect(loggedOut) { if (loggedOut) onLogout() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                ),
            )
        }
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // ── Account section ───────────────────────────────────────────
            SectionLabel("Account")
            InfoRow("Username", username ?: "—")
            InfoRow("Server", serverUrl ?: "—")
            Spacer(Modifier.height(4.dp))
            OutlinedButton(
                onClick = { vm.logout() },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
            ) { Text("Sign out") }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))

            // ── Notifications section ─────────────────────────────────────
            SectionLabel("Alerts")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Enable alerts", Modifier.weight(1f))
                Switch(checked = notifOn, onCheckedChange = { notifOn = it })
            }

            if (notifOn) {
                ThresholdRow("Max temperature (°C)", tMax) { tMax = it }
                ThresholdRow("Min temperature (°C)", tMin) { tMin = it }
                ThresholdRow("Max humidity (%)", hMax) { hMax = it }
                ThresholdRow("Min humidity (%)", hMin) { hMin = it }
            }

            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    vm.saveNotifications(
                        notifOn,
                        tMax.toFloatOrNull() ?: 40f,
                        tMin.toFloatOrNull() ?: 5f,
                        hMax.toFloatOrNull() ?: 90f,
                        hMin.toFloatOrNull() ?: 20f,
                    )
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
            ) { Text("Save", color = MaterialTheme.colorScheme.onPrimary) }
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(text, style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold)
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun ThresholdRow(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
    )
}
