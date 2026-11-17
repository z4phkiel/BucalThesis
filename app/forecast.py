"""Next year's enrollment forecast and how well it did on past years, from the yearly metrics.

Plain pandas and scikit-learn, with no Flask, database or clock: give it the YearlyMetric rows oldest first
(anything with id, school_year, abnormal_reason and the METRIC_FIELDS works) and the school year now under way.
routes.py passes these in for the dashboard and the statistics page.
"""
import math

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# The yearly figures a school submits, as YearlyMetric's columns. routes.py checks the same fields on the metric form.
METRIC_FIELDS = [
    'enrollee_count', 'promotion_rate', 'cohort_survival_rate',
    'completion_rate', 'transition_rate', 'dropout_rate',
    'graduation_rate', 'retention_rate',
]

# The model's inputs: this year's count, the share of students who stay, and how well the school holds students over time
FORECAST_RATES = ['retention_rate', 'cohort_survival_rate']
FORECAST_FEATURES = ['enrollee_count', *FORECAST_RATES]

MIN_FORECAST_YEARS = 9      # usable years needed to forecast or score, which leaves at least 4 past predictions to score
MIN_BACKTEST_YEARS = 5      # fewest earlier years a past prediction is trained on; must stay below MIN_FORECAST_YEARS
RANGE_SHARE = 0.8          # share of past misses the forecast range is built to cover
FEW_TESTS = 10             # with fewer past predictions than this, the scores can't prove which method is better
FAR_INPUT_SDS = 3          # an input this many standard deviations from the training years' average gets a warning

# What the model is scored against, from the same past years. The simplest comes first, so it wins a tie.
RIVAL_FEATURES = ['enrollee_count']     # the same model without the two rates, which shows whether the rates help
METHODS = {
    'baseline_mape': "copying the previous year's count",
    'count_only_mape': 'the model without the two rates',
    'mape': 'the model',
}


def _new_forecast_model():
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0))


def _far_inputs(train_X, row):
    """The inputs in row that are far from every value the model was trained on, where its straight line is a guess."""
    distance = ((row.iloc[0] - train_X.mean()) / train_X.std(ddof=0)).abs()
    return [name.replace('_', ' ') for name in train_X.columns if distance[name] > FAR_INPUT_SDS]


def _predicted_count(model, row):
    """The model's prediction for one row, as a whole number of enrollees that can't be negative."""
    return max(0, round(float(model.predict(row)[0])))


def _forecast_frame(metrics_oldest_first):
    """One row per calendar year, plus which of those years the model can use."""
    df = pd.DataFrame([{
        'id': m.id,
        'school_year': m.school_year,
        'abnormal_reason': m.abnormal_reason,
        **{field: getattr(m, field) for field in METRIC_FIELDS},
    } for m in metrics_oldest_first])
    df[METRIC_FIELDS] = df[METRIC_FIELDS].apply(pd.to_numeric, errors='coerce')
    df['start_year'] = df['school_year'].str.split('-').str[0].str.strip().astype(int)

    # One row per calendar year, so shift() can't pair non-consecutive years. Blank rows sort first, so a duplicate keeps
    # its submitted row; of two submitted rows the later entry (higher id) is kept, since it is the correction
    df = df.sort_values('id').sort_values('enrollee_count', key=pd.notna, kind='stable')
    df = df.drop_duplicates('start_year', keep='last').set_index('start_year').sort_index()
    df = df.reindex(range(df.index.min(), df.index.max() + 1))

    # A year's count and rates are submitted together, so they predict the next year's count
    df['next_enrollee_count'] = df['enrollee_count'].shift(-1)

    # Only the rates the model uses need to be filled in
    has_count = df['enrollee_count'] > 0
    is_complete = (df[FORECAST_RATES] > 0).all(axis=1)

    # An abnormal year misleads the model both as the inputs and as the count to predict, so neither pairing is used
    df['is_abnormal'] = df['abnormal_reason'].fillna('').ne('')
    is_normal_pair = ~(df['is_abnormal'] | df['is_abnormal'].shift(-1, fill_value=False))
    train_df = df[has_count & is_complete & (df['next_enrollee_count'] > 0) & is_normal_pair]
    return df, has_count, is_complete, train_df


def _backtest(train_df):
    """Predict each past year from a model trained only on the years before it, as a real forecast would be."""
    X = train_df[FORECAST_FEATURES]
    y = train_df['next_enrollee_count']

    tests = []
    for i in range(MIN_BACKTEST_YEARS, len(train_df)):
        model = _new_forecast_model().fit(X.iloc[:i], y.iloc[:i])
        predicted = _predicted_count(model, X.iloc[[i]])
        rival = _new_forecast_model().fit(X[RIVAL_FEATURES].iloc[:i], y.iloc[:i])
        actual = int(y.iloc[i])
        tests.append({
            'start_year': int(train_df.index[i]) + 1,
            'predicted': predicted,
            'count_only': _predicted_count(rival, X[RIVAL_FEATURES].iloc[[i]]),
            'actual': actual,
            'previous_count': int(X['enrollee_count'].iloc[i]),
            'earlier_average': float(y.iloc[:i].mean()),
            'trained_on': i,
            'difference': predicted - actual,
            'percent_off': round(abs(predicted - actual) / actual * 100, 1),
        })
    return tests


def _score_backtest(tests):
    """The figures both pages report, all from the same past predictions."""
    misses = sorted(abs(test['difference']) for test in tests)
    covered = min(len(tests), math.ceil((len(tests) + 1) * RANGE_SHARE))
    baseline = [abs(test['previous_count'] - test['actual']) / test['actual'] * 100 for test in tests]
    count_only = [abs(test['count_only'] - test['actual']) / test['actual'] * 100 for test in tests]

    # R2 against guessing the average of the earlier years, since the test years' own average wasn't known yet.
    # That is an easy rival on a trending school, so the pages lead with the average miss beside the two rivals instead.
    model_error = sum(test['difference'] ** 2 for test in tests)
    average_error = sum((test['actual'] - test['earlier_average']) ** 2 for test in tests)

    scores = {
        'mape': round(sum(test['percent_off'] for test in tests) / len(tests), 1),
        'baseline_mape': round(sum(baseline) / len(baseline), 1),
        'count_only_mape': round(sum(count_only) / len(count_only), 1),
        # Above 0 the model ran high, below 0 low: Ridge pulls a growing or shrinking school toward its past average
        'average_difference': round(sum(test['difference'] for test in tests) / len(tests)),
        'r2_score': round(1 - model_error / average_error, 2) if average_error else None,
        'tested_years': len(tests),
        'few_tests': len(tests) < FEW_TESTS,
        'range_margin': misses[covered - 1],
        'range_covered': covered,
    }
    scores['best_method'] = METHODS[min(METHODS, key=scores.get)]
    return scores


def forecast_values(metrics_oldest_first, current_start_year):
    """Train the model on the yearly metrics and return what the dashboard and statistics pages show.
    current_start_year is the first calendar year of the school year now under way (2026 for 2026-2027)."""
    pred_next_year = None
    based_on_year = None
    target_year = None
    forecast_note = None
    forecast_warning = None
    abnormal_years = 0
    actual_year = None
    actual_count = None
    range_low = None
    range_high = None
    forecast_inputs = None
    tests = []
    trained_years = 0
    scores = dict.fromkeys(['mape', 'baseline_mape', 'count_only_mape', 'average_difference', 'r2_score', 'tested_years',
                            'few_tests', 'range_margin', 'range_covered', 'best_method'])

    if metrics_oldest_first:
        df, has_count, is_complete, train_df = _forecast_frame(metrics_oldest_first)
        features = FORECAST_FEATURES
        abnormal_years = int(df['is_abnormal'].sum())
        trained_years = len(train_df)
        tests = _backtest(train_df)

        # The same minimum as the forecast, so both pages report scores under one rule
        if len(train_df) >= MIN_FORECAST_YEARS:
            scores = _score_backtest(tests)

        if has_count.any():
            anchor = int(df.index[has_count][-1])   # latest recorded enrollment
            target_year = f'{anchor + 1}-{anchor + 2}'
            based_on_year = f'{anchor}-{anchor + 1}'

            # Show the current year's submitted count; until then, the forecast year's actual is pending
            if anchor >= current_start_year:
                actual_year = based_on_year
                actual_count = int(df.loc[anchor, 'enrollee_count'])
            else:
                actual_year = target_year

            # if len(train_df) <= len(features):
            #     forecast_note = (
            #         f'Not enough complete years: the model has {len(features)} inputs '
            #         f'but only {len(train_df)} usable years.'
            #     )

            if not is_complete.loc[anchor]:
                forecast_note = (
                    f'No forecast yet: S.Y. {based_on_year} has a blank or 0% retention or cohort survival rate. '
                    'Complete that year to see the forecast.'
                )

            elif len(train_df) < MIN_FORECAST_YEARS:
                forecast_note = (
                    f'Not enough complete years: the forecast needs {MIN_FORECAST_YEARS} usable years '
                    f'but there are only {len(train_df)}.'
                )

            else:
                X = train_df[features]
                y = train_df['next_enrollee_count']

                model = _new_forecast_model().fit(X, y)
                pred_next_year = _predicted_count(model, df.loc[[anchor], features])
                forecast_inputs = {name: float(df.loc[anchor, name]) for name in features}    # for the forecast record
                range_low = max(0, pred_next_year - scores['range_margin'])
                range_high = pred_next_year + scores['range_margin']

                # The forecast still shows, since the model can't tell a real change from a typo, but not without a warning
                doubts = []
                if df.loc[anchor, 'is_abnormal']:
                    doubts.append(f'S.Y. {based_on_year} is marked as an abnormal year.')
                # A growing school's count is a new high every year, so its change from the year before is checked instead
                checked = df[features].assign(enrollee_count=df['enrollee_count'].diff())
                checked = checked.rename(columns={'enrollee_count': 'change_in_enrollee_count'})
                far = _far_inputs(checked.loc[X.index], checked.loc[[anchor]])
                if far:
                    doubts.append(f"S.Y. {based_on_year}'s {' and '.join(far)} {'is' if len(far) == 1 else 'are'} "
                                  'far from anything in the years the model learned from.')
                if doubts:
                    forecast_warning = ' '.join(doubts) + ' Treat this forecast as less reliable than usual.'

    return {
        'pred_next_year': pred_next_year,
        'based_on_year': based_on_year,
        'target_year': target_year,
        'forecast_note': forecast_note,
        'forecast_warning': forecast_warning,
        'abnormal_years': abnormal_years,
        'actual_year': actual_year,
        'actual_count': actual_count,
        'range_low': range_low,
        'range_high': range_high,
        'forecast_inputs': forecast_inputs,
        'tests': tests,
        'trained_years': trained_years,
        **scores,
    }


def prediction_history(metrics_oldest_first, current_start_year):
    """The dashboard's forecast and scores, plus each year's actual count beside its past prediction."""
    forecast = forecast_values(metrics_oldest_first, current_start_year)
    history = {**forecast, 'years': [], 'min_years': MIN_BACKTEST_YEARS}
    if not metrics_oldest_first:
        return history

    df, has_count, _, _ = _forecast_frame(metrics_oldest_first)
    actual = {int(year): int(df.loc[year, 'enrollee_count']) for year in df.index[has_count]}
    abnormal = {int(year): df.loc[year, 'abnormal_reason'] for year in df.index[df['is_abnormal']]}
    tested = {test['start_year']: test for test in forecast['tests']}

    forecast_year = None
    if forecast['pred_next_year'] is not None:
        forecast_year = int(forecast['target_year'].split('-')[0])

    known = sorted({*actual, *tested, *([forecast_year] if forecast_year else [])})
    if not known:
        return history

    # Every calendar year stays on the list, so a missing year shows as a gap in the chart
    for year in range(known[0], known[-1] + 1):
        test = tested.get(year, {})
        is_forecast = year == forecast_year
        left_out = None     # why a year in the middle of the history has no past prediction
        if year in abnormal:
            left_out = 'Not predicted: marked as an abnormal year'
        elif year - 1 in abnormal:
            left_out = 'Not predicted: the year before it was abnormal'
        history['years'].append({
            'id': int(df.loc[year, 'id']) if year in actual else None,     # only a year with a count can be marked abnormal
            'abnormal_reason': abnormal.get(year),
            'left_out': left_out,
            'year': f'{year}-{year + 1}',
            'actual': actual.get(year),
            'predicted': forecast['pred_next_year'] if is_forecast else test.get('predicted'),
            'trained_on': forecast['trained_years'] if is_forecast else test.get('trained_on'),
            'is_forecast': is_forecast,
            'difference': test.get('difference'),
            'percent_off': test.get('percent_off'),
            'range': [forecast['range_low'], forecast['range_high']] if is_forecast else None,
        })
    return history
