import json
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.models import (
    SignalRecord,
    FilterResultRecord,
    ManualOutcomeRecord,
    BacktestRunRecord,
    BacktestTradeRecord,
)
from app.data.manager import market_data_manager
from app.strategy.engine import strategy_engine
from app.backtesting.engine import calculate_wilson_score_interval
from app.schemas.schemas import ManualOutcomeCreate
from app.core.config import settings

class SignalService:
    def __init__(self):
        pass

    def evaluate_pending_signals(self, db: Session, symbol: str) -> int:
        """
        Paper Trading Signal Tracker:
        Finds all unevaluated signals whose 5-minute expiry time has passed (expiry_time <= now),
        looks up the actual candle close at expiry, and determines WIN / LOSS / TIE.
        """
        now = datetime.datetime.utcnow()
        pending = (
            db.query(SignalRecord)
            .filter(
                SignalRecord.symbol == symbol,
                SignalRecord.is_evaluated == False,
                SignalRecord.direction.in_(["CALL", "PUT"]),
                SignalRecord.expiry_time <= now,
            )
            .all()
        )

        if not pending:
            return 0

        # Fetch recent M1 candles to find expiry prices
        df_m1, _ = market_data_manager.get_candles(symbol, "M1", count=60)
        if df_m1.empty:
            return 0

        evaluated_count = 0
        for sig in pending:
            # Find candle closest to sig.expiry_time
            matching_candles = df_m1[df_m1["timestamp"] >= sig.expiry_time]
            if matching_candles.empty:
                # Still waiting for this candle to close
                continue

            expiry_candle = matching_candles.iloc[0]
            expiry_price = float(expiry_candle["close"])
            sig.evaluation_price = expiry_price
            sig.is_evaluated = True
            sig.evaluated_at = datetime.datetime.utcnow()

            if sig.direction == "CALL":
                if expiry_price > sig.entry_price:
                    sig.algorithmic_outcome = "WIN"
                elif expiry_price < sig.entry_price:
                    sig.algorithmic_outcome = "LOSS"
                else:
                    sig.algorithmic_outcome = "TIE"

            elif sig.direction == "PUT":
                if expiry_price < sig.entry_price:
                    sig.algorithmic_outcome = "WIN"
                elif expiry_price > sig.entry_price:
                    sig.algorithmic_outcome = "LOSS"
                else:
                    sig.algorithmic_outcome = "TIE"

            evaluated_count += 1

        if evaluated_count > 0:
            db.commit()

        return evaluated_count

    def analyze_and_record(
        self,
        db: Session,
        symbol: str,
        timeframe: str = "M1",
    ) -> Dict[str, Any]:
        """
        Full analysis pipeline:
          1. Evaluates any past pending signals
          2. Fetches M1, M5, M15 candles
          3. Audits data quality
          4. Evaluates 5 filters & decision logic
          5. Saves or retrieves signal record in database
        """
        # Step 1: Evaluate past pending signals for paper trading
        self.evaluate_pending_signals(db, symbol)

        # Step 2: Fetch multi-timeframe candles
        df_m1, report_m1 = market_data_manager.get_candles(symbol, "M1", count=120)
        df_m5, _ = market_data_manager.get_candles(symbol, "M5", count=80)
        df_m15, _ = market_data_manager.get_candles(symbol, "M15", count=60)

        data_source = market_data_manager.get_active_provider().source_name

        # Step 3: Run strategy engine
        analysis = strategy_engine.analyze(
            symbol=symbol,
            df_m1=df_m1,
            df_m5=df_m5,
            df_m15=df_m15,
            data_source=data_source,
            data_quality_status=report_m1.status,
        )

        sig_id = analysis["id"]
        direction = analysis["direction"]

        # Step 4: Check if signal already exists (prevent duplicate records)
        existing = db.query(SignalRecord).filter(SignalRecord.id == sig_id).first()
        if existing:
            res_dict = self._format_signal_dict(existing)
            res_dict["fear_and_greed"] = analysis.get("fear_and_greed")
            res_dict["currency_strength"] = analysis.get("currency_strength")
            res_dict["micro_timing_tip"] = analysis.get("micro_timing_tip")
            return res_dict

        # Create new record
        sig_rec = SignalRecord(
            id=sig_id,
            symbol=symbol,
            direction=direction,
            created_at=analysis["created_at"],
            entry_price=analysis["entry_price"],
            expiry_time=analysis["expiry_time"],
            data_source=data_source,
            timeframe=timeframe,
            rule_agreement_score=analysis["rule_agreement_score"],
            strategy_version=analysis["strategy_version"],
            data_quality_status=analysis["data_quality_status"],
            decision_reason=analysis["decision_reason"],
            is_evaluated=False if direction in ["CALL", "PUT"] else True,
            algorithmic_outcome="PENDING" if direction in ["CALL", "PUT"] else None,
        )
        db.add(sig_rec)

        # Add filter results
        for f in analysis["filters"]:
            f_rec = FilterResultRecord(
                signal_id=sig_id,
                filter_number=f["filter_number"],
                filter_name=f["filter_name"],
                status=f["status"],
                detected_direction=f["detected_direction"],
                indicator_values=json.dumps(f["indicator_values"]),
                explanation=f["explanation"],
            )
            db.add(f_rec)

        db.commit()
        db.refresh(sig_rec)

        res_dict = self._format_signal_dict(sig_rec)
        res_dict["fear_and_greed"] = analysis.get("fear_and_greed")
        res_dict["currency_strength"] = analysis.get("currency_strength")
        res_dict["micro_timing_tip"] = analysis.get("micro_timing_tip")
        return res_dict

    def get_signals(
        self,
        db: Session,
        symbol: Optional[str] = None,
        direction: Optional[str] = None,
        is_evaluated: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = db.query(SignalRecord)
        if symbol:
            query = query.filter(SignalRecord.symbol == symbol)
        if direction:
            query = query.filter(SignalRecord.direction == direction)
        if is_evaluated is not None:
            query = query.filter(SignalRecord.is_evaluated == is_evaluated)

        records = query.order_by(desc(SignalRecord.created_at)).limit(limit).all()
        return [self._format_signal_dict(r) for r in records]

    def get_signal_by_id(self, db: Session, signal_id: str) -> Optional[Dict[str, Any]]:
        sig = db.query(SignalRecord).filter(SignalRecord.id == signal_id).first()
        if not sig:
            return None
        return self._format_signal_dict(sig)

    def record_manual_outcome(
        self,
        db: Session,
        signal_id: str,
        data: ManualOutcomeCreate,
    ) -> Dict[str, Any]:
        sig = db.query(SignalRecord).filter(SignalRecord.id == signal_id).first()
        if not sig:
            raise ValueError(f"سیگنال با شناسه {signal_id} یافت نشد.")

        # Check existing manual outcome
        existing = db.query(ManualOutcomeRecord).filter(ManualOutcomeRecord.signal_id == signal_id).first()
        if existing:
            existing.observed_entry_price = data.observed_entry_price
            existing.observed_expiry_price = data.observed_expiry_price
            existing.observed_time = data.observed_time
            existing.user_reported_outcome = data.user_reported_outcome
            existing.price_source_description = data.price_source_description or "Quotex Manual Observation"
            existing.notes = data.notes
            rec = existing
        else:
            rec = ManualOutcomeRecord(
                signal_id=signal_id,
                observed_entry_price=data.observed_entry_price,
                observed_expiry_price=data.observed_expiry_price,
                observed_time=data.observed_time,
                user_reported_outcome=data.user_reported_outcome,
                price_source_description=data.price_source_description or "Quotex Manual Observation",
                notes=data.notes,
            )
            db.add(rec)

        db.commit()
        db.refresh(rec)
        db.refresh(sig)
        return self._format_signal_dict(sig)

    def get_analytics_summary(self, db: Session) -> Dict[str, Any]:
        """
        Calculates aggregate metrics for both Algorithmic evaluations (Paper Trading)
        and Manual Quotex Outcomes (separately, as strictly mandated!).
        """
        signals = db.query(SignalRecord).filter(SignalRecord.direction.in_(["CALL", "PUT"])).all()
        total_signals = len(signals)

        # Algorithmic evaluation stats
        algo_evaluated = [s for s in signals if s.is_evaluated and s.algorithmic_outcome in ["WIN", "LOSS", "TIE"]]
        algo_wins = sum(1 for s in algo_evaluated if s.algorithmic_outcome == "WIN")
        algo_losses = sum(1 for s in algo_evaluated if s.algorithmic_outcome == "LOSS")
        algo_ties = sum(1 for s in algo_evaluated if s.algorithmic_outcome == "TIE")
        algo_total_decided = algo_wins + algo_losses

        algo_win_rate = round(algo_wins / algo_total_decided * 100.0, 2) if algo_total_decided > 0 else 0.0
        wilson = calculate_wilson_score_interval(algo_wins, algo_total_decided, 0.95)
        algo_net_return = round((algo_wins * settings.DEFAULT_PAYOUT_RATIO) - algo_losses, 2)

        # Manual Quotex outcomes
        manuals = db.query(ManualOutcomeRecord).all()
        man_wins = sum(1 for m in manuals if m.user_reported_outcome == "WIN")
        man_losses = sum(1 for m in manuals if m.user_reported_outcome == "LOSS")
        man_ties = sum(1 for m in manuals if m.user_reported_outcome == "TIE")
        man_decided = man_wins + man_losses
        man_win_rate = round(man_wins / man_decided * 100.0, 2) if man_decided > 0 else 0.0

        # Per-symbol stats
        symbol_stats = {}
        for sym in settings.SUPPORTED_SYMBOLS:
            sym_sigs = [s for s in algo_evaluated if s.symbol == sym]
            s_w = sum(1 for s in sym_sigs if s.algorithmic_outcome == "WIN")
            s_l = sum(1 for s in sym_sigs if s.algorithmic_outcome == "LOSS")
            s_tot = s_w + s_l
            symbol_stats[sym] = {
                "total": len(sym_sigs),
                "wins": s_w,
                "losses": s_l,
                "win_rate": round(s_w / s_tot * 100.0, 2) if s_tot > 0 else 0.0,
            }

        recent_records = (
            db.query(SignalRecord)
            .order_by(desc(SignalRecord.created_at))
            .limit(15)
            .all()
        )

        return {
            "total_signals": total_signals,
            "evaluated_signals": len(algo_evaluated),
            "algorithmic_win_rate": algo_win_rate,
            "algorithmic_wilson_lower": wilson["lower"],
            "algorithmic_wilson_upper": wilson["upper"],
            "algorithmic_net_return": algo_net_return,
            "manual_logged_trades": len(manuals),
            "manual_win_rate": man_win_rate,
            "manual_wins": man_wins,
            "manual_losses": man_losses,
            "manual_ties": man_ties,
            "recent_signals": [self._format_signal_dict(r) for r in recent_records],
            "symbol_stats": symbol_stats,
        }

    def _format_signal_dict(self, sig: SignalRecord) -> Dict[str, Any]:
        filters_list = []
        for f in sig.filters:
            ind_val = {}
            if f.indicator_values:
                try:
                    ind_val = json.loads(f.indicator_values)
                except Exception:
                    ind_val = {}
            filters_list.append({
                "filter_number": f.filter_number,
                "filter_name": f.filter_name,
                "status": f.status,
                "detected_direction": f.detected_direction,
                "indicator_values": ind_val,
                "explanation": f.explanation,
            })

        man_dict = None
        if sig.manual_outcome:
            m = sig.manual_outcome
            man_dict = {
                "id": m.id,
                "signal_id": m.signal_id,
                "observed_entry_price": m.observed_entry_price,
                "observed_expiry_price": m.observed_expiry_price,
                "observed_time": m.observed_time,
                "user_reported_outcome": m.user_reported_outcome,
                "price_source_description": m.price_source_description,
                "notes": m.notes,
                "recorded_at": m.recorded_at,
            }

        return {
            "id": sig.id,
            "symbol": sig.symbol,
            "direction": sig.direction,
            "created_at": sig.created_at,
            "entry_price": sig.entry_price,
            "expiry_time": sig.expiry_time,
            "data_source": sig.data_source,
            "timeframe": sig.timeframe,
            "rule_agreement_score": sig.rule_agreement_score,
            "strategy_version": sig.strategy_version,
            "data_quality_status": sig.data_quality_status,
            "decision_reason": sig.decision_reason,
            "is_evaluated": sig.is_evaluated,
            "evaluation_price": sig.evaluation_price,
            "algorithmic_outcome": sig.algorithmic_outcome,
            "evaluated_at": sig.evaluated_at,
            "filters": filters_list,
            "manual_outcome": man_dict,
        }

signal_service = SignalService()
