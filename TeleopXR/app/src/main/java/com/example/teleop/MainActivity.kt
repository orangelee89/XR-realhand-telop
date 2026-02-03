package com.example.teleop

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CornerSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.tooling.preview.PreviewLightDark
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.xr.arcore.RenderViewpoint
import androidx.xr.compose.platform.LocalSession
import androidx.xr.compose.platform.LocalSpatialCapabilities
import androidx.xr.compose.platform.LocalSpatialConfiguration
import androidx.xr.compose.spatial.ContentEdge
import androidx.xr.compose.spatial.Orbiter
import androidx.xr.compose.spatial.Subspace
import androidx.xr.compose.subspace.DragPolicy
import androidx.xr.compose.subspace.MovePolicy
import androidx.xr.compose.subspace.ResizePolicy
import androidx.xr.compose.subspace.SpatialPanel
import androidx.xr.compose.subspace.layout.SpatialRoundedCornerShape
import androidx.xr.compose.subspace.layout.SubspaceModifier
import androidx.xr.compose.subspace.layout.height
import androidx.xr.compose.subspace.layout.width
import androidx.xr.runtime.Config
import androidx.xr.runtime.Session
import androidx.xr.runtime.SessionConfigureSuccess
import com.example.teleop.ui.theme.TeleopTheme
import kotlinx.coroutines.awaitCancellation

class MainActivity : ComponentActivity() {

    @SuppressLint("RestrictedApi")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.d(LOGCAT_TAG, "onCreate")
        enableEdgeToEdge()

        setContent {
            TeleopTheme {
                val spatialConfiguration = LocalSpatialConfiguration.current
                val isSpatialUiEnabled = LocalSpatialCapabilities.current.isSpatialUiEnabled
                Log.i(LOGCAT_TAG, "isSpatialUiEnabled: $isSpatialUiEnabled")
                if (isSpatialUiEnabled) {
                    Log.i(LOGCAT_TAG, "Using 3D space")
                    Subspace {
                        MySpatialContent(
                            onRequestHomeSpaceMode = spatialConfiguration::requestHomeSpaceMode
                        )
                    }
                } else {
                    Log.i(LOGCAT_TAG, "Using 2D space instead")
                    My2DContent(onRequestFullSpaceMode = spatialConfiguration::requestFullSpaceMode)
                }
            }
        }
    }

    companion object {
        private const val LOGCAT_TAG = "MainActivity"
    }
}

@SuppressLint("RestrictedApi")
@Composable
fun MySpatialContent(
    onRequestHomeSpaceMode: () -> Unit,
    teleopViewModel: TeleopViewModel = viewModel()
) {
    val session = LocalSession.current
    val lifecycleOwner = LocalLifecycleOwner.current

    ConfigureHeadAndHandTracking(session)

    LaunchedEffect(session, lifecycleOwner.lifecycle) {
        Log.d(LOGCAT_TAG, "init spatial content composable, session: $session")
        if (session == null)
            return@LaunchedEffect
        lifecycleOwner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            teleopViewModel.start(session)
            awaitCancellation()
        }
    }
    DisposableEffect(Unit) {
        onDispose { teleopViewModel.stop() }
    }

    val left = teleopViewModel.leftHand.collectAsState().value
    val right = teleopViewModel.rightHand.collectAsState().value
    val headPose = teleopViewModel.headPose.collectAsState().value

    SpatialPanel(SubspaceModifier.width(1280.dp).height(800.dp), dragPolicy = MovePolicy(isEnabled = true), resizePolicy = ResizePolicy(isEnabled = true)) {
        Surface {
            MainContent(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(48.dp)
            )
        }
        Orbiter(
            position = ContentEdge.Top,
            offset = 20.dp,
            alignment = Alignment.End,
            shape = SpatialRoundedCornerShape(CornerSize(28.dp))
        ) {
            HomeSpaceModeIconButton(
                onClick = onRequestHomeSpaceMode,
                modifier = Modifier.size(56.dp)
            )
        }
    }
}

@Composable
private fun ConfigureHeadAndHandTracking(session: Session?) {
    var configured by remember { mutableStateOf(false) }

    LaunchedEffect(session) {
        Log.d(LOGCAT_TAG, "config hand tracking, session: $session, configured: $configured")
        if (session != null && !configured) {
            val newConfig = session.config.copy(
                handTracking = Config.HandTrackingMode.BOTH,
                headTracking = Config.HeadTrackingMode.LAST_KNOWN
            )
            when(val result = session.configure(newConfig)) {
                is SessionConfigureSuccess -> {
                    Log.d(LOGCAT_TAG, "Hand tracking configured successfully")
                    configured = true
                    val mono = RenderViewpoint.mono(session)
                    Log.i(LOGCAT_TAG, "mono after successful configuring: $mono")
                } else -> {
                    Log.e(LOGCAT_TAG, "Failed to configure hand tracking: $result")
                    configured = false
                }
            }
        }
    }

    DisposableEffect(session) {
        onDispose {
            configured = false
        }
    }
}

@SuppressLint("RestrictedApi")
@Composable
fun My2DContent(onRequestFullSpaceMode: () -> Unit) {
    val session = LocalSession.current
    val teleopViewModel: TeleopViewModel = viewModel()

    // Configure hand tracking FIRST
    ConfigureHeadAndHandTracking(session)

    // Auto-start hand tracking after config
    LaunchedEffect(session) {
        if (session == null) return@LaunchedEffect
        // Wait a bit for config to complete
        kotlinx.coroutines.delay(500)
        teleopViewModel.setTargetHost("192.168.1.132")
        teleopViewModel.setTargetPort(5000)
        teleopViewModel.start(session)
    }

    DisposableEffect(Unit) {
        onDispose { teleopViewModel.stop() }
    }

    // Use exact same UI as original app
    Surface {
        Row(
            modifier = Modifier.fillMaxSize(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            MainContent(modifier = Modifier.padding(48.dp))
            if (!LocalInspectionMode.current && LocalSession.current != null) {
                FullSpaceModeIconButton(
                    onClick = onRequestFullSpaceMode,
                    modifier = Modifier.padding(32.dp)
                )
            }
        }
    }
}

@Composable
fun MainContent(modifier: Modifier = Modifier) {
    Text(text = stringResource(R.string.hello_android_xr), modifier = modifier)
}

@Composable
fun FullSpaceModeIconButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    IconButton(onClick = onClick, modifier = modifier) {
        Icon(
            painter = painterResource(id = R.drawable.ic_full_space_mode_switch),
            contentDescription = stringResource(R.string.switch_to_full_space_mode)
        )
    }
}

@Composable
fun HomeSpaceModeIconButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    FilledTonalIconButton(onClick = onClick, modifier = modifier) {
        Icon(
            painter = painterResource(id = R.drawable.ic_home_space_mode_switch),
            contentDescription = stringResource(R.string.switch_to_home_space_mode)
        )
    }
}

@PreviewLightDark
@Composable
fun My2dContentPreview() {
    TeleopTheme {
        My2DContent(onRequestFullSpaceMode = {})
    }
}

@Preview(showBackground = true)
@Composable
fun FullSpaceModeButtonPreview() {
    TeleopTheme {
        FullSpaceModeIconButton(onClick = {})
    }
}

@PreviewLightDark
@Composable
fun HomeSpaceModeButtonPreview() {
    TeleopTheme {
        HomeSpaceModeIconButton(onClick = {})
    }
}

private const val LOGCAT_TAG = "MainActivity"