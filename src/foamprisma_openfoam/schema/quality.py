"""
Mesh quality metrics with auto-generated quality assessment visualizations.
"""

from nomad.metainfo import MSection, Quantity, Section
from nomad.datamodel.metainfo.plot import PlotSection, PlotlyFigure
import plotly.graph_objects as go
import numpy as np


class MeshQuality(PlotSection):
    """
    Mesh quality metrics from checkMesh output.
    Rendered as visual quality indicators on the entry overview page.
    """

    m_def = Section()

    # ── Orthogonality ──
    max_non_orthogonality = Quantity(
        type=np.float64,
        description='Maximum non-orthogonality angle (degrees)',
    )
    average_non_orthogonality = Quantity(
        type=np.float64,
        description='Average non-orthogonality angle (degrees)',
    )

    # ── Skewness ──
    max_skewness = Quantity(
        type=np.float64,
        description='Maximum cell skewness',
    )

    # ── Aspect ratio ──
    max_aspect_ratio = Quantity(
        type=np.float64,
        description='Maximum cell aspect ratio',
    )

    # ── Volume ──
    min_volume = Quantity(
        type=np.float64,
        description='Minimum cell volume (m³)',
    )
    max_volume = Quantity(
        type=np.float64,
        description='Maximum cell volume (m³)',
    )

    # ── Overall ──
    mesh_ok = Quantity(
        type=bool,
        description='Whether checkMesh reports "Mesh OK"',
    )
    n_illegal_cells = Quantity(
        type=int,
        description='Number of cells with negative volume or other failures',
        default=0,
    )

    def normalize(self, archive, logger):
        super().normalize(archive, logger)

        metrics = {}
        thresholds = {}

        if self.max_non_orthogonality is not None:
            metrics['Non-Orthogonality (max)'] = self.max_non_orthogonality
            thresholds['Non-Orthogonality (max)'] = 70.0  # degrees

        if self.max_skewness is not None:
            metrics['Skewness (max)'] = self.max_skewness
            thresholds['Skewness (max)'] = 4.0

        if self.max_aspect_ratio is not None:
            metrics['Aspect Ratio (max)'] = self.max_aspect_ratio
            thresholds['Aspect Ratio (max)'] = 100.0

        if not metrics:
            return

        # ── Build quality gauge chart ──
        names = list(metrics.keys())
        values = list(metrics.values())
        threshold_vals = [thresholds.get(n, 100) for n in names]

        # Normalize to 0-100 scale (100 = at threshold, beyond = bad)
        normalized = [min((v / t) * 100, 150) for v, t in zip(values, threshold_vals)]
        colors = ['#00B894' if n <= 80 else '#FF6B35' if n <= 100 else '#DC2626'
                  for n in normalized]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=names,
            y=normalized,
            marker_color=colors,
            text=[f'{v:.1f}' for v in values],
            textposition='outside',
            hovertemplate='%{x}<br>Value: %{text}<br>Threshold: %{customdata:.1f}<extra></extra>',
            customdata=threshold_vals,
        ))

        # Add threshold line
        fig.add_hline(y=100, line_dash='dash', line_color='red',
                      annotation_text='Threshold', annotation_position='top left')

        fig.update_layout(
            title='Mesh Quality Assessment',
            yaxis_title='% of Threshold (lower is better)',
            template='plotly_white',
            height=400,
            showlegend=False,
        )

        status = '✓ Mesh OK' if self.mesh_ok else '✗ Mesh has issues'

        self.figures = [
            PlotlyFigure(
                label=f'Mesh Quality ({status})',
                figure=fig.to_plotly_json(),
            ),
        ]
