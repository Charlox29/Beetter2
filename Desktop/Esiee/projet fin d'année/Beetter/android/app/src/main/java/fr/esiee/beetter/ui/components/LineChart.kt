package fr.esiee.beetter.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

@Composable
fun BeeterLineChart(
    points: List<Double?>,
    modifier: Modifier = Modifier,
    lineColor: Color = MaterialTheme.colorScheme.primary,
    unit: String = "",
) {
    val nonNull = points.mapNotNull { it?.toFloat() }

    if (nonNull.isEmpty()) {
        Box(modifier.fillMaxWidth().height(120.dp), contentAlignment = Alignment.Center) {
            Text("No data", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }

    val minVal = nonNull.min()
    val maxVal = nonNull.max()
    val range = (maxVal - minVal).coerceAtLeast(0.01f)
    val midVal = (minVal + maxVal) / 2f

    Row(modifier.fillMaxWidth().height(140.dp)) {
        // Y-axis labels
        Column(
            Modifier.width(44.dp).fillMaxHeight().padding(end = 4.dp, bottom = 4.dp),
            verticalArrangement = Arrangement.SpaceBetween,
            horizontalAlignment = Alignment.End,
        ) {
            Text("%.1f%s".format(maxVal, unit), style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("%.1f%s".format(midVal, unit), style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("%.1f%s".format(minVal, unit), style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        // Chart canvas
        val gridColor = Color.Gray.copy(alpha = 0.15f)
        Canvas(Modifier.weight(1f).fillMaxHeight()) {
            val w = size.width
            val h = size.height
            val n = (points.size - 1).coerceAtLeast(1)

            // Horizontal grid lines at 0 %, 50 %, 100 %
            listOf(0f, 0.5f, 1f).forEach { pct ->
                val y = h * (1f - pct)
                drawLine(gridColor, Offset(0f, y), Offset(w, y), strokeWidth = 1.dp.toPx())
            }

            // Build fill path and line path
            val fillPath = Path()
            val linePath = Path()
            var started = false
            var lastX = 0f

            points.forEachIndexed { i, v ->
                if (v == null) { started = false; return@forEachIndexed }
                val x = i.toFloat() / n * w
                val y = h * (1f - (v.toFloat() - minVal) / range)
                if (!started) {
                    fillPath.moveTo(x, h)
                    fillPath.lineTo(x, y)
                    linePath.moveTo(x, y)
                    started = true
                } else {
                    fillPath.lineTo(x, y)
                    linePath.lineTo(x, y)
                }
                lastX = x
            }
            if (started) {
                fillPath.lineTo(lastX, h)
                fillPath.close()
            }

            drawPath(fillPath, color = lineColor.copy(alpha = 0.15f))
            drawPath(linePath, color = lineColor, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round))
        }
    }
}
