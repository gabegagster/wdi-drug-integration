# Data fusion experiment skeleton

Create a new folder under `notebooks/`, copy the skeleton notebook into it,
and rename the notebook for your experiment. Update `work_dir` in the setup
cell to your new folder, for example:

```python
work_dir = project_root / 'notebooks/my_fusion_experiment'
```

Figures and CSV results will then stay in that experiment folder.

The [notebook](data_fusion_skeleton.ipynb) provides a starting point for testing
fusion rules on the medicine evaluation CSV. It currently runs one baseline
fusion rule as a placeholder and reports density, consistency, and accuracy.

## Set up experiments

At the start of your notebook, describe your experiment setup: which rules
you will test, why you chose them, the evaluation data, and the comparisons
you plan to make.

Change the `fusion_rules` dictionary in the **Fusion rules** section to assign
the resolution function for each attribute. The current configuration uses
longest string for text, voting for categories and counts, and union for sets.

```python
fusion_rules = {
    'brandName': longest_string,
    'activeSubstances': union,
    'activeSubstanceCount': voting,
    'licenceHolder': longest_string,
    'productClass': voting,
    'atcCode': union,
    'dosageForm': union,
    'route': union,
    'strengths': union,
    'biosimilar': voting,
}
```

Run the notebook from top to bottom to generate the metrics, figures, and error
table. Outputs are saved in this folder.

## PyDI rule options

`DataFusionStrategy('my_experiment')` takes a descriptive name string. Assign
imported rule functions to attributes; the rule values in `fusion_rules` are
function objects. Import additional functions from `PyDI.fusion` as needed.

| Type | Available functions |
|---|---|
| Text | `longest_string`, `shortest_string`, `most_complete` |
| Categories | `voting`, `weighted_voting` |
| Numbers | `average`, `median`, `minimum`, `maximum`, `sum_values` |
| Dates | `earliest`, `most_recent` |
| Lists / sets | `union`, `intersection`, `intersection_k_sources` |
| Source preference | `favour_sources`, `prefer_higher_trust` |

Choose functions that fit the attribute's datatype and meaning. Strength
amounts in this notebook are text or ranges paired with units; numeric
functions need additional preparation before use on these values.

The notebook registers each rule with
`strategy.add_attribute_fuser(attribute, rule)`. You can pass rule-specific
options here, such as a source order:

```python
from PyDI.fusion import favour_sources

strategy.add_attribute_fuser(
    'licenceHolder', favour_sources,
    source_preferences=['FDA', 'EMA', 'DPD'],
)
```

Place an attribute-specific override after the registration loop in **Run
fusion** so it takes effect. Use `add_evaluation_function` to configure how
fused and gold values are compared.

See the official [PyDI fusion guide](https://github.com/wbsg-uni-mannheim/PyDI/blob/main/docs/wiki/DataFusion.md)
for rule descriptions, parameters, strategy configuration, and custom resolvers.

## Complex rules

Define a custom function in a function-definition cell, then assign it in
`fusion_rules`. A resolver accepts `values` and `**kwargs` and returns
`(fused_value, confidence, metadata)`. PyDI also supplies source IDs, source
datasets, and available trust metadata for source-aware decisions.

For example, vote on complete ingredient sets after normalizing case and order:

```python
def vote_ingredient_sets(values, **kwargs):
    """Select the most frequent normalized ingredient set."""
    # Normalize Sets
    ingredient_sets = [
        tuple(sorted({name.strip().casefold() for name in names}))
        for names in values
    ]

    # Vote
    selected, confidence, metadata = voting(ingredient_sets)
    return list(selected), confidence, metadata


fusion_rules['activeSubstances'] = vote_ingredient_sets
```

Keep the function definition separate from the assignment cell. Explain the
rule's rationale and tie handling in the experiment setup. Resolver confidence
is separate from measured accuracy against gold values.

**Missing values:** dedicated missing-value fusion rules have not been set up
yet. The notebook currently uses PyDI's default behavior: available values can
fill gaps, and attributes with no available input value remain missing.

## Metrics

- **Density:** populated attribute cells / total attribute cells. Reported by
  attribute for each source and the fused sample.
- **Consistency:** groups with agreeing source values / groups with available
  values, per attribute. One available value counts as agreement.
- **Accuracy:** correct fused values / gold values, per attribute and overall.
  The experiment assumes a completed gold worksheet.

## Extend the study

You can ask an agent to extend the current setup to compare multiple fusion
rules within the notebook, including visualizations, measures, and tables
showing their differences by attribute and overall performance.

Include an **Observations and conclusions** section at the end. Summarize the
main findings, explain remaining errors, and state which rules worked best
and why, including the limits of the evaluation sample.
