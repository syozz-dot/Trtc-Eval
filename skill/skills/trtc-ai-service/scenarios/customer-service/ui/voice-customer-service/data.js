/* ===== PRODUCT & ORDER DATA ===== */
window.AppData = {
  cos: {
    s1: 'https://venus-vedas-1258344701.cos-internal.ap-guangzhou.tencentcos.cn//formal/20260611/vedas-formal-pod-20260611105642-192b18/2d87829d-c873-40b1-9ea7-b6f8e1068ea5-v1.png',
    s2: 'https://venus-vedas-1258344701.cos-internal.ap-guangzhou.tencentcos.cn//formal/20260611/vedas-formal-pod-20260611105642-192b18/4f3d823c-0224-44b8-899c-e0e257f8d7ad-v1.jpg',
    s3: 'https://venus-vedas-1258344701.cos-internal.ap-guangzhou.tencentcos.cn//formal/20260611/vedas-formal-pod-20260611105642-192b18/837f061f-810d-4cb2-82df-b989147f7342-v1.jpg',
    s4: 'https://venus-vedas-1258344701.cos-internal.ap-guangzhou.tencentcos.cn//formal/20260611/vedas-formal-pod-20260611105642-192b18/5ac97853-ff60-472a-a492-0e2d22b2589a-v1.jpg',
    s5: 'https://venus-vedas-1258344701.cos-internal.ap-guangzhou.tencentcos.cn//formal/20260611/vedas-formal-pod-20260611105642-192b18/67a42c48-3cb5-4b2d-9dfb-f2467dd90d0c-v1.jpg',
  },
  products: [
    { id: 'p1', name: 'AirRun Pro Cushion Runner',     price: 129, img: 's1', tag: 'Hot',      tagCls: 'tag-hot' },
    { id: 'p2', name: 'CloudWalk Lite Daily Sneaker',  price: 79,  img: 's2', tag: 'In stock', tagCls: 'tag-instock' },
    { id: 'p3', name: 'TrailEdge All-Terrain Hiker',   price: 159, img: 's3', tag: 'In stock', tagCls: 'tag-instock' },
    { id: 'p4', name: 'CourtZero Tennis Trainer',      price: 99,  img: 's4', tag: 'Low stock', tagCls: 'tag-low' },
    { id: 'p5', name: 'UrbanFlex Slip-On',             price: 65,  img: 's5', tag: 'Hot',      tagCls: 'tag-hot' },
    { id: 'p6', name: 'NightGlow Reflective Runner',   price: 139, img: 's1', tag: 'In stock', tagCls: 'tag-instock' },
    { id: 'p7', name: 'BreezeMesh Summer Walker',      price: 69,  img: 's2', tag: 'In stock', tagCls: 'tag-instock' },
    { id: 'p8', name: 'PeakStorm Waterproof Boot',     price: 179, img: 's3', tag: 'Low stock', tagCls: 'tag-low' },
  ],
  orders: [
    { id: '1122033', date: 'Jan 5, 2026',  pidx: 0, qty: 1, status: 'Delivered',  cls: 'b-delivered' },
    { id: '1122034', date: 'Jan 12, 2026', pidx: 1, qty: 2, status: 'Shipped',    cls: 'b-shipped' },
    { id: '1122035', date: 'Jan 18, 2026', pidx: 2, qty: 1, status: 'Processing', cls: 'b-processing' },
    { id: '1122036', date: 'Jan 22, 2026', pidx: 3, qty: 1, status: 'Delivered',  cls: 'b-delivered' },
    { id: '1122037', date: 'Feb 02, 2026', pidx: 4, qty: 3, status: 'Shipped',    cls: 'b-shipped' },
    { id: '1122038', date: 'Feb 08, 2026', pidx: 5, qty: 1, status: 'Processing', cls: 'b-processing' },
    { id: '1122039', date: 'Feb 14, 2026', pidx: 6, qty: 2, status: 'Delivered',  cls: 'b-delivered' },
  ],
  greeting: "Hello! I'm your AI assistant powered by TRTC Conversational AI. You can ask about any product on the left, check your orders, or request a refund. Just speak naturally.",
  farewell: "Thank you for calling. Have a great day. Goodbye!"
};

// Resolve image paths
(function() {
  var d = window.AppData;
  d.products.forEach(function(p) {
    var src = d.cos[p.img];
    p.img = src || 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><rect fill="#f0e6ff" width="200" height="200"/><text x="100" y="110" text-anchor="middle" fill="#9b7bf7" font-size="16">' + p.name.substring(0,20) + '</text></svg>');
  });
})();
