package fr.esiee.beetter.ui.detail

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.esiee.beetter.ui.components.BeeterLineChart

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BeehiveDetailScreen(
    beehiveId: String,
    onBack: () -> Unit,
    vm: BeehiveDetailViewModel = viewModel(),
) {
    val state by vm.state.collectAsState()

    LaunchedEffect(beehiveId) { vm.load(beehiveId) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Beehive #$beehiveId", fontWeight = FontWeight.Bold) },
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
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Range selector
            RangeSelector(
                selected = state.range,
                onSelect = { vm.load(beehiveId, it) },
            )

            when {
                state.isLoading -> Box(Modifier.fillMaxWidth().height(200.dp),
                    contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.error != null -> Text(state.error!!, color = MaterialTheme.colorScheme.error)
                state.data != null -> {
                    val data = state.data!!

                    ChartCard(
                        title = "Temperature",
                        unit = "°C",
                        color = MaterialTheme.colorScheme.error,
                        points = data.temperature?.data ?: emptyList(),
                    )
                    ChartCard(
                        title = "Humidity",
                        unit = "%",
                        color = Color(0xFF1565C0),
                        points = data.humidity?.data ?: emptyList(),
                    )
                }
            }
        }
    }
}

@Composable
private fun RangeSelector(selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        RANGES.forEach { range ->
            FilterChip(
                selected = range == selected,
                onClick = { onSelect(range) },
                label = { Text(range) },
            )
        }
    }
}

@Composable
private fun ChartCard(title: String, unit: String, color: Color, points: List<Double?>) {
    Card(elevation = CardDefaults.cardElevation(2.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            BeeterLineChart(
                points = points,
                lineColor = color,
                unit = unit,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
