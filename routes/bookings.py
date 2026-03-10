from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Booking, Facility, Notification
from datetime import date, datetime

bookings = Blueprint('bookings', __name__)


@bookings.route('/bookings')
@login_required
def list_bookings():
    if current_user.is_admin():
        all_bookings = Booking.query.order_by(Booking.created_at.desc()).all()
        return render_template('bookings/all_bookings.html', bookings=all_bookings)
    my_bookings = Booking.query.filter_by(user_id=current_user.id)\
                      .order_by(Booking.created_at.desc()).all()
    return render_template('bookings/my_bookings.html', bookings=my_bookings)


@bookings.route('/bookings/create', methods=['GET', 'POST'])
@login_required
def create_booking():
    all_facilities = Facility.query.filter_by(is_available=True).all()

    if request.method == 'POST':
        facility_id  = request.form.get('facility_id')
        title        = request.form.get('title', '').strip()
        reason       = request.form.get('reason', '').strip()
        bdate_str    = request.form.get('booking_date', '')
        stime_str    = request.form.get('start_time', '')
        etime_str    = request.form.get('end_time', '')
        attendees    = request.form.get('attendees', 1)
        is_draft     = request.form.get('save_draft') == '1'

        
        if not all([facility_id, title, reason, bdate_str, stime_str, etime_str]):
            flash('All fields are required.', 'danger')
            return render_template('bookings/create.html', facilities=all_facilities)

        
        try:
            booking_date = datetime.strptime(bdate_str, '%Y-%m-%d').date()
            start_time   = datetime.strptime(stime_str, '%H:%M').time()
            end_time     = datetime.strptime(etime_str, '%H:%M').time()
        except ValueError:
            flash('Invalid date or time format.', 'danger')
            return render_template('bookings/create.html', facilities=all_facilities)

        if booking_date < date.today():
            flash('Booking date cannot be in the past.', 'danger')
            return render_template('bookings/create.html', facilities=all_facilities)

        if start_time >= end_time:
            flash('End time must be after start time.', 'danger')
            return render_template('bookings/create.html', facilities=all_facilities)

        
        facility = Facility.query.get(facility_id)
        if not facility:
            flash('Facility not found.', 'danger')
            return render_template('bookings/create.html', facilities=all_facilities)

        if int(attendees) > facility.capacity:
            flash(f'Number of attendees exceeds facility capacity ({facility.capacity}).', 'warning')

        
        if not is_draft:
            conflicts = Booking.check_conflict(facility_id, booking_date, start_time, end_time)
            if conflicts:
                flash('This facility is already booked during that time slot.', 'danger')
                return render_template('bookings/create.html', facilities=all_facilities)

        status  = 'draft' if is_draft else 'pending'
        booking = Booking(
            user_id      = current_user.id,
            facility_id  = int(facility_id),
            title        = title,
            reason       = reason,
            booking_date = booking_date,
            start_time   = start_time,
            end_time     = end_time,
            attendees    = int(attendees),
            status       = status,
        )
        db.session.add(booking)
        db.session.commit()

        if not is_draft:
            
            from models import User
            admins = User.query.filter_by(role='admin').all()
            for a in admins:
                db.session.add(Notification(
                    user_id    = a.id,
                    message    = f'New booking request: "{title}" by {current_user.full_name} '
                                 f'for {facility.name} on {booking_date}.',
                    type       = 'info',
                    booking_id = booking.id,
                ))
            db.session.commit()
            flash('Booking submitted! Awaiting admin approval.', 'success')
        else:
            flash('Booking saved as draft.', 'info')

        return redirect(url_for('bookings.list_bookings'))

    return render_template('bookings/create.html', facilities=all_facilities)


@bookings.route('/bookings/<int:booking_id>')
@login_required
def booking_detail(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if not current_user.is_admin() and booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('bookings.list_bookings'))
    return render_template('bookings/booking_detail.html', booking=booking)


@bookings.route('/bookings/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if not current_user.is_admin() and booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('bookings.list_bookings'))

    if booking.status in ['pending', 'approved', 'draft']:
        booking.status = 'cancelled'
        db.session.add(Notification(
            user_id    = booking.user_id,
            message    = f'Your booking "{booking.title}" has been cancelled.',
            type       = 'warning',
            booking_id = booking.id,
        ))
        db.session.commit()
        flash('Booking cancelled.', 'info')
    else:
        flash('This booking cannot be cancelled.', 'danger')

    return redirect(url_for('bookings.list_bookings'))


@bookings.route('/bookings/<int:booking_id>/submit', methods=['POST'])
@login_required
def submit_draft(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('bookings.list_bookings'))

    if booking.status == 'draft':
        conflicts = Booking.check_conflict(
            booking.facility_id, booking.booking_date,
            booking.start_time,  booking.end_time,
            exclude_id=booking.id)
        if conflicts:
            flash('Cannot submit: time slot conflict detected.', 'danger')
            return redirect(url_for('bookings.booking_detail', booking_id=booking.id))

        booking.status = 'pending'
        db.session.commit()

        from models import User
        admins = User.query.filter_by(role='admin').all()
        for a in admins:
            db.session.add(Notification(
                user_id    = a.id,
                message    = f'New booking request: "{booking.title}" by {current_user.full_name}.',
                type       = 'info',
                booking_id = booking.id,
            ))
        db.session.commit()
        flash('Draft submitted for approval.', 'success')

    return redirect(url_for('bookings.list_bookings'))


@bookings.route('/api/availability')
@login_required
def check_availability():
    facility_id  = request.args.get('facility_id')
    booking_date = request.args.get('date')
    if not facility_id or not booking_date:
        return jsonify({'bookings': []})
    try:
        d = datetime.strptime(booking_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'bookings': []})
    day_bookings = Booking.query.filter_by(
        facility_id=facility_id, booking_date=d, status='approved').all()
    return jsonify({'bookings': [
        {'title': b.title,
         'start': b.start_time.strftime('%H:%M'),
         'end':   b.end_time.strftime('%H:%M')}
        for b in day_bookings
    ]})
