package fr.esiee.beetter.ui.login

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.*
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun LoginScreen(
    onLoginSuccess: () -> Unit,
    vm: LoginViewModel = viewModel(),
) {
    val state by vm.state.collectAsState()
    val savedUrl by vm.savedServerUrl.collectAsState(initial = "")

    var serverUrl by remember(savedUrl) { mutableStateOf(savedUrl ?: "") }
    var username  by remember { mutableStateOf("") }
    var password  by remember { mutableStateOf("") }
    var showPass  by remember { mutableStateOf(false) }

    LaunchedEffect(state) {
        if (state is LoginState.Success) onLoginSuccess()
    }

    Box(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Card(
            modifier = Modifier.fillMaxWidth().widthIn(max = 400.dp),
            elevation = CardDefaults.cardElevation(4.dp),
        ) {
            Column(
                modifier = Modifier.padding(28.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("🐝 Beetter", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text("Sign in to your account", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)

                Spacer(Modifier.height(4.dp))

                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = { serverUrl = it },
                    label = { Text("Server URL") },
                    placeholder = { Text("https://your-server.com") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                )
                OutlinedTextField(
                    value = username,
                    onValueChange = { username = it },
                    label = { Text("Username") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Password") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = if (showPass) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        IconButton(onClick = { showPass = !showPass }) {
                            Icon(
                                if (showPass) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                contentDescription = if (showPass) "Hide password" else "Show password",
                            )
                        }
                    },
                )

                if (state is LoginState.Error) {
                    Text(
                        (state as LoginState.Error).message,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                Button(
                    onClick = { vm.login(serverUrl, username, password) },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = state !is LoginState.Loading,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                ) {
                    if (state is LoginState.Loading) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp,
                            color = MaterialTheme.colorScheme.onPrimary)
                    } else {
                        Text("Sign in", color = MaterialTheme.colorScheme.onPrimary)
                    }
                }
            }
        }
    }
}
