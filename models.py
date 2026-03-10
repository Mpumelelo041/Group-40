from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


# ─────────────────────────────────────────────────────────────
#  User
# ─────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id             = db.Column(db.Integer,     primary_key=True)
    student_number = db.Column(db.String(20),  unique=True, nullable=False)
    name           = db.Column(db.String(100), nullable=False)
    surname        = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    role           = db.Column(db.String(20),  nullable=False, default='student')
    is_active      = db.Column(db.Boolean,     default=True)
    created_at     = db.Column(db.DateTime,    default=datetime.utcnow)

    bookings      = db.relationship('Booking',      backref='user',     lazy='dynamic')
    notifications = db.relationship('Notification', backref='user',     lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.name} {self.surname}"

    def is_admin(self):
        return self.role == 'admin'

    def is_staff(self):
        return self.role in ['staff', 'admin']

    def __repr__(self):
        return f'<User {self.student_number} [{self.role}]>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────────────────────
#  Facility
# ─────────────────────────────────────────────────────────────
class Facility(db.Model):
    __tablename__ = 'facilities'

    id            = db.Column(db.Integer,     primary_key=True)
    name          = db.Column(db.String(150), nullable=False)
    facility_type = db.Column(db.String(50),  nullable=False)   # lab | hall | sports | lecture_room
    location      = db.Column(db.String(200), nullable=False)
    capacity      = db.Column(db.Integer,     nullable=False)
    description   = db.Column(db.Text)
    equipment     = db.Column(db.Text)                          # comma-separated string
    is_available  = db.Column(db.Boolean,     default=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    bookings = db.relationship('Booking', backref='facility', lazy='dynamic')

    @property
    def equipment_list(self):
        if self.equipment:
            return [e.strip() for e in self.equipment.split(',')]
        return []

    def __repr__(self):
        return f'<Facility {self.name}>'


# ─────────────────────────────────────────────────────────────
#  Booking
# ─────────────────────────────────────────────────────────────
class Booking(db.Model):
    __tablename__ = 'bookings'

    id           = db.Column(db.Integer,     primary_key=True)
    user_id      = db.Column(db.Integer,     db.ForeignKey('users.id'),      nullable=False)
    facility_id  = db.Column(db.Integer,     db.ForeignKey('facilities.id'), nullable=False)
    title        = db.Column(db.String(200), nullable=False)
    reason       = db.Column(db.Text,        nullable=False)
    booking_date = db.Column(db.Date,        nullable=False)
    start_time   = db.Column(db.Time,        nullable=False)
    end_time     = db.Column(db.Time,        nullable=False)
    attendees    = db.Column(db.Integer,     default=1)
    status       = db.Column(db.String(20),  default='pending')   # pending | approved | rejected | cancelled | draft
    admin_notes  = db.Column(db.Text)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def check_conflict(facility_id, booking_date, start_time, end_time, exclude_id=None):
        """Return approved bookings that overlap the requested time slot."""
        query = Booking.query.filter(
            Booking.facility_id  == facility_id,
            Booking.booking_date == booking_date,
            Booking.status       == 'approved',
            Booking.start_time   <  end_time,
            Booking.end_time     >  start_time,
        )
        if exclude_id:
            query = query.filter(Booking.id != exclude_id)
        return query.all()

    @property
    def duration_hours(self):
        start = datetime.combine(self.booking_date, self.start_time)
        end   = datetime.combine(self.booking_date, self.end_time)
        return (end - start).seconds / 3600

    def __repr__(self):
        return f'<Booking {self.id} – {self.title} [{self.status}]>'


# ─────────────────────────────────────────────────────────────
#  Notification
# ─────────────────────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer,    primary_key=True)
    user_id    = db.Column(db.Integer,    db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.Text,       nullable=False)
    type       = db.Column(db.String(30), default='info')   # info | success | warning | danger
    is_read    = db.Column(db.Boolean,    default=False)
    booking_id = db.Column(db.Integer,    db.ForeignKey('bookings.id'), nullable=True)
    created_at = db.Column(db.DateTime,   default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification {self.id} → user {self.user_id}>'
