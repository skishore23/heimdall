"""
Dev command: TUI dashboard

A beautiful terminal UI for Heimdall development and monitoring.
Inspired by modern CLI tools with Norse mythology aesthetics.
"""

import asyncio
from typing import Any

import typer
from rich.console import Console

console = Console()


def dev_command() -> None:
    """
    Launch interactive TUI dashboard

    Features:
    - Bifröst Gateway status monitoring
    - Live trace streaming
    - Guard registry browser
    - Performance metrics visualization
    - Policy composition viewer

    Requires: pip install textual
    """
    try:
        from rich.panel import Panel
        from rich.table import Table as RichTable
        from rich.text import Text
        from textual.app import App, ComposeResult
        from textual.containers import Container, Horizontal, Vertical
        from textual.reactive import reactive
        from textual.widgets import Footer, Header, Static
        from textual.worker import Worker

        from bifrost.client import BifrostClient
        from heimdall_cli.config import HeimdallConfig

    except ImportError as e:
        if "textual" in str(e).lower():
            console.print("[red]✗[/red] Textual not installed", style="bold")
            console.print("Install with: pip install 'heimdall[cli]'")
        else:
            console.print(f"[red]✗[/red] Import error: {e}", style="bold")
        raise typer.Exit(1)

    # Define TUI classes inside function where imports are available
    class ConnectionBanner(Static):
        """Banner showing connection status to Bifrost"""

        connected: reactive[bool] = reactive(False)
        url: reactive[str] = reactive("")

        def render(self) -> Panel:
            """Render connection banner"""
            if self.connected:
                text = Text()
                text.append("✓ ", style="bold green")
                text.append("Connected to Bifröst Gateway", style="bold bright_white")
                text.append(f" ({self.url})", style="dim")
                return Panel(text, border_style="bright_green", padding=(0, 2))
            else:
                text = Text()
                text.append("⚠ ", style="bold yellow")
                text.append("Bifröst Gateway Offline", style="bold bright_yellow")
                text.append(f" ({self.url})", style="dim")
                text.append("\n\n", style="")
                text.append("Start the gateway with: ", style="dim")
                text.append("heimdall-gateway", style="cyan bold")
                return Panel(text, border_style="bright_yellow", padding=(1, 2))

    class StatusIndicator(Static):
        """Animated status indicator with color"""

        status: reactive[str] = reactive("unknown")

        def __init__(self, label: str = "", **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.label = label

        def render(self) -> Text:
            """Render status with color and symbol"""
            status_map = {
                "healthy": ("●", "bright_green", "ONLINE"),
                "degraded": ("●", "bright_yellow", "DEGRADED"),
                "unhealthy": ("●", "bright_red", "OFFLINE"),
                "unknown": ("○", "dim", "UNKNOWN"),
            }
            symbol, color, display_status = status_map.get(
                self.status, ("?", "white", self.status.upper())
            )

            text = Text()
            text.append(symbol + " ", style=color)
            text.append(self.label, style="bold bright_white")
            text.append(": ", style="dim")
            text.append(display_status, style=color)
            return text

    class MetricsPanel(Static):
        """Panel displaying system metrics"""

        metrics: reactive[dict[str, Any]] = reactive(dict)

        def render(self) -> Panel:
            """Render metrics in a beautiful panel"""
            if not self.metrics:
                empty_text = Text("─ Waiting for metrics ─", style="dim italic", justify="center")
                return Panel(
                    empty_text,
                    title="⚡ [bold cyan]Performance Metrics[/bold cyan]",
                    border_style="bright_blue",
                    padding=(1, 2),
                )

            table = RichTable.grid(padding=(0, 2))
            table.add_column(style="bright_cyan bold", no_wrap=True, width=18)
            table.add_column(style="bright_white", justify="right")

            total_requests = self.metrics.get("gateway_requests_total", 0)
            avg_duration = self.metrics.get("gateway_request_duration_seconds", 0)

            table.add_row("🌉 Requests", f"[bold]{total_requests:,}[/bold]")
            table.add_row("⏱️  Avg Duration", f"[yellow]{avg_duration:.3f}s[/yellow]")

            guard_metrics = self.metrics.get("guard_performance_metrics", {})
            if guard_metrics:
                total_execs = guard_metrics.get("total_executions", 0)
                avg_time = guard_metrics.get("average_execution_time_ms", 0)
                table.add_row("", "")
                table.add_row("🛡️  Guard Execs", f"[bold]{total_execs:,}[/bold]")
                table.add_row("⚡ Guard Time", f"[green]{avg_time:.2f}ms[/green]")

            return Panel(
                table,
                title="⚡ [bold cyan]Performance Metrics[/bold cyan]",
                border_style="bright_blue",
                padding=(1, 1),
            )

    class TraceStream(Static):
        """Live trace streaming display"""

        traces: reactive[list[dict[str, Any]]] = reactive(list, layout=True)

        def render(self) -> Panel:
            """Render recent traces"""
            if not self.traces:
                empty_text = Text("─ Awaiting trace data ─", style="dim italic", justify="center")
                content = empty_text
            else:
                table = RichTable.grid(padding=(0, 2))
                table.add_column(style="bold", width=7)
                table.add_column(style="bright_cyan", width=32)
                table.add_column(style="dim", width=12, justify="right")

                for trace in self.traces[-10:]:
                    decision = trace.get("decision", "unknown")
                    guard_id = trace.get("guard_id", "unknown")
                    duration = trace.get("duration_ms", 0)

                    if decision == "pass":
                        decision_text = "[bold green]✓ PASS[/bold green]"
                    elif decision == "block":
                        decision_text = "[bold red]✗ BLOCK[/bold red]"
                    else:
                        decision_text = "[bold yellow]? UNKN[/bold yellow]"

                    display_guard_id = guard_id[:30] + "..." if len(guard_id) > 30 else guard_id

                    if duration < 50:
                        duration_text = f"[green]{duration:.1f}ms[/green]"
                    elif duration < 150:
                        duration_text = f"[yellow]{duration:.1f}ms[/yellow]"
                    else:
                        duration_text = f"[red]{duration:.1f}ms[/red]"

                    table.add_row(decision_text, display_guard_id, duration_text)

                content = table

            return Panel(
                content,
                title="🔍 [bold magenta]Live Decision Traces[/bold magenta]",
                border_style="bright_magenta",
                padding=(1, 1),
            )

    class GuardRegistry(Static):
        """Guard registry browser"""

        guards: reactive[list[dict[str, Any]]] = reactive(list, layout=True)

        def render(self) -> Panel:
            """Render guard registry"""
            if not self.guards:
                try:
                    import guards  # noqa: F401
                    from heimdall.registry import REGISTRY

                    guard_list = []
                    for guard_id, metadata in sorted(REGISTRY.items()):
                        guard_list.append({
                            "id": guard_id,
                            "tier": metadata.tier or "T1",
                            "description": metadata.description or "",
                        })
                    self.guards = guard_list
                except Exception:
                    pass

            if not self.guards:
                empty_text = Text("─ No guards registered ─", style="dim italic", justify="center")
                content = empty_text
            else:
                table = RichTable.grid(padding=(0, 2))
                table.add_column(style="bright_cyan bold", width=28)
                table.add_column(style="yellow bold", width=6, justify="center")
                table.add_column(style="dim", width=38)

                table.add_row(
                    "[bold underline]Guard ID[/bold underline]",
                    "[bold underline]Tier[/bold underline]",
                    "[bold underline]Description[/bold underline]"
                )

                for guard in self.guards[:12]:
                    guard_id = guard.get("id", "")
                    tier = guard.get("tier", "T1")
                    desc = guard.get("description", "")[:36]

                    display_id = guard_id[:26] + ".." if len(guard_id) > 26 else guard_id

                    tier_style = {
                        "T0": "[bright_green]",
                        "T1": "[bright_yellow]",
                        "T2": "[bright_red]",
                    }.get(tier, "[white]")

                    table.add_row(display_id, f"{tier_style}{tier}[/{tier_style.strip('[]')}]", desc)

                if len(self.guards) > 12:
                    table.add_row("[dim]...[/dim]", "", f"[dim]({len(self.guards) - 12} more)[/dim]")

                content = table

            if self.guards:
                t0 = sum(1 for g in self.guards if g.get("tier") == "T0")
                t1 = sum(1 for g in self.guards if g.get("tier") == "T1")
                t2 = sum(1 for g in self.guards if g.get("tier") == "T2")
                title = f"🛡️  [bold green]Guard Registry[/bold green] [dim]({t0}T0 · {t1}T1 · {t2}T2)[/dim]"
            else:
                title = "🛡️  [bold green]Guard Registry[/bold green]"

            return Panel(content, title=title, border_style="bright_green", padding=(1, 1))

    class PolicyInfo(Static):
        """Policy information display"""

        policy_data: reactive[dict[str, Any] | None] = reactive(None, layout=True)

        def render(self) -> Panel:
            """Render policy information"""
            if not self.policy_data:
                empty_text = Text("─ No policy loaded ─", style="dim italic", justify="center")
                content = empty_text
            else:
                table = RichTable.grid(padding=(0, 1))
                table.add_column(style="bright_yellow bold", no_wrap=True, width=12)
                table.add_column(style="bright_white")

                policy_id = self.policy_data.get("policy_id", "unknown")
                version = self.policy_data.get("version", "unknown")
                guard_count = self.policy_data.get("guard_count", 0)

                table.add_row("📜 Policy:", f"[bold]{policy_id}[/bold]")
                table.add_row("🏷️  Version:", f"[dim]{version}[/dim]")
                table.add_row("🛡️  Guards:", f"[cyan]{guard_count}[/cyan]")

                content = table

            return Panel(
                content,
                title="📜 [bold yellow]Active Policy[/bold yellow]",
                border_style="bright_yellow",
                padding=(0, 1),
            )

    class HeimdallDashboard(App):
        """Heimdall Development Dashboard - Beautiful TUI for monitoring guards and gateway"""

        CSS = """
        Screen {
            background: $surface;
            overflow: hidden;
        }

        Header {
            dock: top;
            height: 3;
            content-align: center middle;
            background: $primary;
            color: $text;
            text-style: bold;
        }

        Footer {
            dock: bottom;
            height: 1;
            background: $panel;
        }

        .main-container {
            layout: vertical;
            height: 100%;
            padding: 1;
            overflow: auto;
        }

        ConnectionBanner {
            height: auto;
            margin-bottom: 1;
        }

        .top-row {
            layout: horizontal;
            height: 14;
            margin-bottom: 1;
        }

        .middle-row {
            layout: horizontal;
            height: 20;
            margin-bottom: 1;
        }

        .bottom-row {
            layout: horizontal;
            height: auto;
            min-height: 18;
        }

        .status-box {
            width: 1fr;
            height: 100%;
            padding: 0;
            margin-right: 1;
        }

        .metrics-box {
            width: 1fr;
            height: 100%;
            padding: 0;
        }

        StatusIndicator {
            height: 1;
            padding: 0 1;
            margin: 0 0 1 0;
        }

        PolicyInfo {
            height: auto;
            margin-top: 1;
        }
        """

        TITLE = "⚔️  H E I M D A L L  - AI Guardian"
        SUB_TITLE = "Development Dashboard • Real-time Guard Monitoring"

        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh", "Refresh"),
            ("t", "toggle_traces", "Toggle Traces"),
            ("g", "toggle_guards", "Toggle Guards"),
            ("d", "toggle_dark", "Dark Mode"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.config = HeimdallConfig()
            self.bifrost_client: BifrostClient | None = None
            self.trace_worker: Worker | None = None
            self.status_worker: Worker | None = None

        def compose(self) -> ComposeResult:
            """Create child widgets"""
            yield Header(show_clock=True)

            with Container(classes="main-container"):
                yield ConnectionBanner(id="connection-banner")

                with Horizontal(classes="top-row"):
                    with Vertical(classes="status-box"):
                        yield StatusIndicator("Bifröst Gateway", id="gateway-status")
                        yield StatusIndicator("Redis Cache", id="redis-status")
                        yield PolicyInfo(id="policy-info")

                    yield MetricsPanel(id="metrics-panel")

                with Horizontal(classes="middle-row"):
                    yield TraceStream(id="trace-stream")

                with Horizontal(classes="bottom-row"):
                    yield GuardRegistry(id="guard-registry")

            yield Footer()

        async def on_mount(self) -> None:
            """Handle app mount"""
            try:
                self.bifrost_client = BifrostClient(self.config.bifrost_url)
            except Exception:
                pass

            self.status_worker = self.update_status_loop()
            self.trace_worker = self.stream_traces_loop()

        @staticmethod
        def format_status(status: str) -> str:
            """Format status string"""
            return status.lower() if status else "unknown"

        async def update_status_loop(self) -> None:
            """Background task to update status"""
            while True:
                connected = False
                try:
                    if self.bifrost_client:
                        status_data = await self.bifrost_client.get_status()
                        connected = True

                        banner = self.query_one("#connection-banner", ConnectionBanner)
                        banner.connected = True
                        banner.url = self.config.bifrost_url

                        gateway_status = self.query_one("#gateway-status", StatusIndicator)
                        health_status = status_data.get("health", {}).get("status", "unknown")
                        gateway_status.status = self.format_status(health_status)

                        redis_status = self.query_one("#redis-status", StatusIndicator)
                        redis_state = status_data.get("health", {}).get("redis", "unknown")
                        redis_status.status = self.format_status(redis_state)

                        metrics_panel = self.query_one("#metrics-panel", MetricsPanel)
                        metrics_panel.metrics = status_data.get("metrics", {})

                        policy_panel = self.query_one("#policy-info", PolicyInfo)
                        info = status_data.get("info", {})
                        config_data = info.get("config", {})
                        policy_panel.policy_data = {
                            "policy_id": config_data.get("default_policy_id", "none"),
                            "version": "latest",
                            "guard_count": len(config_data.get("guards", [])),
                        }
                except Exception:
                    connected = False

                if not connected:
                    try:
                        banner = self.query_one("#connection-banner", ConnectionBanner)
                        banner.connected = False
                        banner.url = self.config.bifrost_url
                    except Exception:
                        pass

                await asyncio.sleep(2)

        async def stream_traces_loop(self) -> None:
            """Background task to stream traces"""
            while True:
                try:
                    if self.bifrost_client:
                        result = await self.bifrost_client.get_trace_list(limit=10)
                        traces = result.get("traces", [])

                        trace_stream = self.query_one("#trace-stream", TraceStream)
                        trace_stream.traces = traces
                except Exception:
                    pass

                await asyncio.sleep(3)

        def action_quit(self) -> None:
            """Quit the application"""
            self.exit()

        async def action_refresh(self) -> None:
            """Refresh all data"""
            if self.bifrost_client:
                try:
                    status_data = await self.bifrost_client.get_status()

                    gateway_status = self.query_one("#gateway-status", StatusIndicator)
                    gateway_status.status = status_data.get("health", {}).get("status", "unknown")

                    metrics_panel = self.query_one("#metrics-panel", MetricsPanel)
                    metrics_panel.metrics = status_data.get("metrics", {})
                except Exception:
                    pass

        def action_toggle_traces(self) -> None:
            """Toggle trace stream visibility"""
            trace_stream = self.query_one("#trace-stream", TraceStream)
            trace_stream.display = not trace_stream.display

        def action_toggle_guards(self) -> None:
            """Toggle guard registry visibility"""
            guard_registry = self.query_one("#guard-registry", GuardRegistry)
            guard_registry.display = not guard_registry.display

    # Run the TUI app
    try:
        app = HeimdallDashboard()
        app.run()
    except Exception as e:
        console.print(f"[red]✗[/red] Dashboard error: {e}", style="bold")
        raise typer.Exit(1)
