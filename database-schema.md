// ---- 1. 基礎主檔模塊（靜態資料） ----

Table Users {
  user_id int [pk, increment]
  email varchar(100) [unique, not null]
  password_hash varchar(255) [not null]
  name varchar(50) [not null]
  phone varchar(20) [not null]
  user_type varchar(20) [note: 'general, corporate, admin']
  tgo_balance int [default: 0]
  created_at timestamp [default: `now()` ]
}

Table Stations {
  station_id int [pk, increment]
  station_name varchar(20) [unique, not null]
  sequence_no int [unique, not null, note: '南港=1, 台北=2...']
  latitude decimal(9,6)
  longitude decimal(9,6)
}

Table Trains {
  train_no varchar(10) [pk]
  train_type varchar(20) [note: 'standard, express']
  total_carriages int [default: 12]
}

Table Seats {
  seat_id int [pk, increment]
  carriage_no int [not null]
  row_no int [not null]
  seat_letter varchar(1) [not null, note: 'A, B, C, D, E']
  is_business_class boolean [default: false]
  
  Note: '實體座位硬體配置'
}

Table Ticket_Prices {
  price_id int [pk, increment]
  start_station_id int [not null]
  end_station_id int [not null]
  is_business boolean [default: false]
  base_price int [not null]
  
  Note: '起訖站原價矩陣表'
}


// ---- 2. 營運時刻與配額模塊（動態資料） ----

Table Schedules {
  schedule_id int [pk, increment]
  train_no varchar(10) [not null]
  departure_date date [not null]
  non_reserved_start_carriage int [default: 10]
  
  Note: '每日營運班次主檔'
}

Table Stop_Times {
  stop_id int [pk, increment]
  schedule_id int [not null]
  station_id int [not null]
  arrival_time time
  departure_time time
  
  Note: '班次中途停靠各站時刻表'
}

Table Early_Bird_Pools {
  pool_id int [pk, increment]
  schedule_id int [not null]
  discount_rate decimal(3,2) [not null, note: '例如 0.65']
  initial_quota int [not null]
  available_quota int [not null]
}


// ---- 3. 交易與核心商務模塊 ----

Table Orders {
  order_id int [pk, increment]
  user_id int [not null]
  booking_code varchar(10) [unique, not null]
  total_amount int [not null]
  payment_status varchar(20) [default: 'unpaid', note: 'unpaid, paid, cancelled']
  created_at timestamp [default: `now()` ]
}

Table Order_Tickets {
  ticket_id int [pk, increment]
  order_id int [not null]
  schedule_id int [not null]
  seat_id int [not null]
  start_station_id int [not null]
  end_station_id int [not null]
  ticket_type varchar(20) [not null, note: '全票, 早鳥, 大學生, 敬老, 愛心, 愛陪, 兒童']
  companion_ticket_id int [note: '愛陪票綁定愛心票的 ticket_id']
  actual_price int [not null]
  ticket_status varchar(20) [default: 'valid']
  
  Note: '車票明細檔（核心，1筆訂單至多6張）'
}


// ---- 4. 創新與回饋模塊 ----

Table Waitlists {
  waitlist_id int [pk, increment]
  user_id int [not null]
  schedule_id int [not null]
  start_station_id int [not null]
  end_station_id int [not null]
  preferred_seat_type varchar(20) [default: 'any']
  status varchar(20) [default: 'waiting']
  created_at timestamp [default: `now()` ]
  
  Note: '智慧退票自動候補機制'
}


// ---- 🔗 關聯關係定義 (Relationships) ----

// 票價矩陣的起訖站連結
Ref: Ticket_Prices.start_station_id > Stations.station_id
Ref: Ticket_Prices.end_station_id > Stations.station_id

// 每日班次連結列車
Ref: Schedules.train_no > Trains.train_no

// 停靠時間的多對多中間表連結
Ref: Stop_Times.schedule_id > Schedules.schedule_id [delete: cascade]
Ref: Stop_Times.station_id > Stations.station_id

// 早鳥配額池連結班次
Ref: Early_Bird_Pools.schedule_id > Schedules.schedule_id [delete: cascade]

// 訂單主檔連結會員
Ref: Orders.user_id > Users.user_id

// 車票明細連結訂單主檔（一對多，至多 6 張）
Ref: Order_Tickets.order_id > Orders.order_id [delete: cascade]
Ref: Order_Tickets.schedule_id > Schedules.schedule_id
Ref: Order_Tickets.seat_id > Seats.seat_id
Ref: Order_Tickets.start_station_id > Stations.station_id
Ref: Order_Tickets.end_station_id > Stations.station_id

// ✨ 亮點：愛陪票綁定同訂單愛心票的「自我關聯」
Ref: Order_Tickets.companion_ticket_id - Order_Tickets.ticket_id

// 智慧候補機制連結
Ref: Waitlists.user_id > Users.user_id
Ref: Waitlists.schedule_id > Schedules.schedule_id
Ref: Waitlists.start_station_id > Stations.station_id
Ref: Waitlists.end_station_id > Stations.station_id


Ref: "Order_Tickets"."ticket_id" < "Order_Tickets"."schedule_id"