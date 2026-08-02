// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2026 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! T-Invest specific types and conversion utilities.

use chrono::{DateTime, Utc};
use rust_decimal::Decimal;

/// Represents a T-Invest Quotation (units + nano).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Quotation {
    pub units: i64,
    pub nano: i32,
}

impl Quotation {
    pub const fn new(units: i64, nano: i32) -> Self {
        Self { units, nano }
    }

    /// Convert to `rust_decimal::Decimal`.
    pub fn to_decimal(&self) -> Decimal {
        Decimal::new(self.units, 0) + Decimal::new(self.nano as i64, 9)
    }

    /// Convert to f64.
    pub fn to_f64(&self) -> f64 {
        self.units as f64 + self.nano as f64 * 1e-9
    }
}

impl From<&crate::proto::Quotation> for Quotation {
    fn from(q: &crate::proto::Quotation) -> Self {
        Self {
            units: q.units,
            nano: q.nano,
        }
    }
}

/// Represents a T-Invest MoneyValue.
#[derive(Debug, Clone, PartialEq)]
pub struct MoneyValue {
    pub units: i64,
    pub nano: i32,
    pub currency: String,
}

impl MoneyValue {
    pub fn to_decimal(&self) -> Decimal {
        Decimal::new(self.units, 0) + Decimal::new(self.nano as i64, 9)
    }
}

impl From<&crate::proto::MoneyValue> for MoneyValue {
    fn from(m: &crate::proto::MoneyValue) -> Self {
        Self {
            units: m.units,
            nano: m.nano,
            currency: m.currency.clone(),
        }
    }
}

/// Convert proto Timestamp to chrono DateTime<Utc>.
pub fn proto_timestamp_to_datetime(ts: &prost_types::Timestamp) -> DateTime<Utc> {
    DateTime::from_timestamp(ts.seconds, ts.nanos as u32).unwrap_or(DateTime::UNIX_EPOCH)
}
