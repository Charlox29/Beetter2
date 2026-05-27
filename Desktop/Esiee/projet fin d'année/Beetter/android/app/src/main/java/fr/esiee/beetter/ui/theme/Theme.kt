package fr.esiee.beetter.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Amber400 = Color(0xFFFFC107)
private val Amber600 = Color(0xFFFFB300)
private val Dark     = Color(0xFF1A1A2E)

private val LightColors = lightColorScheme(
    primary          = Amber600,
    onPrimary        = Color.Black,
    primaryContainer = Color(0xFFFFF3CD),
    secondary        = Dark,
    onSecondary      = Color.White,
    background       = Color(0xFFF8F9FA),
    surface          = Color.White,
)

@Composable
fun BeeterTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        content = content,
    )
}
