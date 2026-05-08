"""
Simulation results schema with built-in Plotly visualization.

When an OpenFOAM case is parsed, the residual data is stored in these sections.
The PlotSection annotations cause NOMAD's GUI to render interactive convergence
plots directly on the entry overview page.
"""

from nomad.metainfo import MSection, Quantity, SubSection, Section
from nomad.datamodel.metainfo.plot import PlotSection, PlotlyFigure
import plotly.graph_objects as go
import numpy as np


class ResidualHistory(MSection):
    """Residual convergence history for a single field variable."""

    field_name = Quantity(
        type=str,
        description='Field variable name (e.g., Ux, Uy, p, k, omega)',
    )
    initial_residuals = Quantity(
        type=np.float64,
        shape=['*'],
        description='Initial residual at each iteration',
    )
    final_residuals = Quantity(
        type=np.float64,
        shape=['*'],
        description='Final residual at each iteration',
    )


class SimulationResults(PlotSection):
    """
    Post-processing results with auto-generated convergence plots.

    Inherits from PlotSection so NOMAD GUI displays plots on the entry overview.
    """

    m_def = Section()

    converged = Quantity(
        type=bool,
        description='Whether the solver reached convergence criteria',
    )
    total_iterations = Quantity(
        type=int,
        description='Total number of solver iterations',
    )
    wall_time_seconds = Quantity(
        type=np.float64,
        unit='second',
        description='Total wall-clock time for the solver run',
    )
    continuity_error_final = Quantity(
        type=np.float64,
        description='Final continuity error',
    )

    residual_histories = SubSection(
        sub_section=ResidualHistory,
        repeats=True,
        description='Per-field residual convergence histories',
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

        if not self.residual_histories:
            return

        # ── Build residual convergence plot ──
        fig_residuals = go.Figure()

        for rh in self.residual_histories:
            if rh.initial_residuals is not None and len(rh.initial_residuals) > 0:
                iterations = list(range(1, len(rh.initial_residuals) + 1))
                fig_residuals.add_trace(go.Scatter(
                    x=iterations,
                    y=rh.initial_residuals.tolist(),
                    mode='lines',
                    name=f'{rh.field_name} (initial)',
                    line=dict(width=1),
                ))

            if rh.final_residuals is not None and len(rh.final_residuals) > 0:
                iterations = list(range(1, len(rh.final_residuals) + 1))
                fig_residuals.add_trace(go.Scatter(
                    x=iterations,
                    y=rh.final_residuals.tolist(),
                    mode='lines',
                    name=f'{rh.field_name} (final)',
                    line=dict(width=1, dash='dot'),
                ))

        fig_residuals.update_layout(
            title='Solver Residual Convergence',
            xaxis_title='Iteration',
            yaxis_title='Residual',
            yaxis_type='log',
            template='plotly_white',
            legend=dict(orientation='h', yanchor='bottom', y=1.02),
            height=450,
        )

        self.figures = [
            PlotlyFigure(
                label='Residual Convergence',
                figure=fig_residuals.to_plotly_json(),
            ),
        ]

        # ── Determine convergence ──
        if self.residual_histories:
            last_residuals = []
            for rh in self.residual_histories:
                if rh.final_residuals is not None and len(rh.final_residuals) > 0:
                    last_residuals.append(rh.final_residuals[-1])
            if last_residuals:
                self.converged = all(r < 1e-4 for r in last_residuals)

        # ── Set total iterations from longest residual history ──
        if self.residual_histories:
            max_iters = max(
                len(rh.initial_residuals) if rh.initial_residuals is not None else 0
                for rh in self.residual_histories
            )
            if max_iters > 0:
                self.total_iterations = max_iters
