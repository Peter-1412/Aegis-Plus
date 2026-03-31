# 前端开发经典错误示例

这个文件包含了前端开发中常见的经典错误，用于教学和学习目的。

## 📋 错误分类

### 1️⃣ TypeScript 类型相关错误

**错误 1-2: 使用 `any` 类型**
```typescript
// ❌ 错误示例
function fetchData(url: any): any {
  return fetch(url).then(res => res.json());
}

// ✅ 正确做法
interface ApiResponse {
  data: unknown;
  status: number;
}

function fetchData(url: string): Promise<ApiResponse> {
  return fetch(url).then(res => ({
    data: res.json(),
    status: res.status
  }));
}
```

### 2️⃣ React Hooks 相关错误

**错误 3-4: 状态初始化问题**
```typescript
// ❌ 错误示例
const [data, setData] = useState(null);
const [error, setError] = useState(null);

// ✅ 正确做法
const [data, setData] = useState<User | null>(null);
const [error, setError] = useState<Error | null>(null);
```

**错误 5-6: useEffect 中的异步函数**
```typescript
// ❌ 错误示例
useEffect(async () => {
  const data = await fetchData();
  setData(data);
}, []);

// ✅ 正确做法
useEffect(() => {
  const fetchData = async () => {
    const data = await fetchApi();
    setData(data);
  };
  fetchData();
}, []);
```

**错误 7: 缺少依赖数组**
```typescript
// ❌ 错误示例
useEffect(() => {
  fetchData();
}); // 每次渲染都会执行

// ✅ 正确做法
useEffect(() => {
  fetchData();
}, []); // 只在挂载时执行
```

**错误 8: 在渲染时修改状态**
```typescript
// ❌ 错误示例
if (data) {
  setData(null); // 在渲染过程中修改状态
}

// ✅ 正确做法
useEffect(() => {
  if (data) {
    setData(null);
  }
}, [data]);
```

### 3️⃣ 内存泄漏错误

**错误 11: 未清理的定时器**
```typescript
// ❌ 错误示例
useEffect(() => {
  const interval = setInterval(() => {
    console.log("Checking...");
  }, 1000);
  // 缺少清理函数
}, []);

// ✅ 正确做法
useEffect(() => {
  const interval = setInterval(() => {
    console.log("Checking...");
  }, 1000);
  
  return () => clearInterval(interval);
}, []);
```

### 4️⃣ 竞态条件错误

**错误 12: 未处理的竞态条件**
```typescript
// ❌ 错误示例
useEffect(() => {
  fetchData("/api/data").then((result) => {
    setData(result); // 可能是过时的数据
  });
}, []);

// ✅ 正确做法
useEffect(() => {
  let shouldIgnore = false;
  
  fetchData("/api/data").then((result) => {
    if (!shouldIgnore) {
      setData(result);
    }
  });
  
  return () => {
    shouldIgnore = true;
  };
}, []);
```

### 5️⃣ 闭包陷阱

**错误 15: 使用过时的状态值**
```typescript
// ❌ 错误示例
useEffect(() => {
  const timer = setTimeout(() => {
    console.log(`Count: ${count}`); // 捕获的是初始值
  }, 5000);
  
  return () => clearTimeout(timer);
}, []); // 缺少 count 依赖

// ✅ 正确做法
useEffect(() => {
  const timer = setTimeout(() => {
    console.log(`Count: ${count}`);
  }, 5000);
  
  return () => clearTimeout(timer);
}, [count]); // 添加 count 依赖
```

### 6️⃣ 回调地狱

**错误 13: 过度嵌套的回调**
```typescript
// ❌ 错误示例
fetch("/api/user")
  .then(res => {
    res.json().then(data => {
      fetch(`/api/posts/${data.id}`)
        .then(res => {
          res.json().then(posts => {
            posts.forEach(post => {
              fetch(`/api/comments/${post.id}`)
                .then(res => res.json())
                .then(comments => {
                  console.log(comments);
                });
            });
          });
        });
    });
  });

// ✅ 正确做法
async function fetchUserData() {
  const userRes = await fetch("/api/user");
  const user = await userRes.json();
  
  const postsRes = await fetch(`/api/posts/${user.id}`);
  const posts = await postsRes.json();
  
  const commentsPromises = posts.map(post =>
    fetch(`/api/comments/${post.id}`).then(res => res.json())
  );
  
  const comments = await Promise.all(commentsPromises);
  console.log(comments);
}
```

### 7️⃣ 状态更新错误

**错误 10: 直接修改状态对象**
```typescript
// ❌ 错误示例
data.user = { name: "new name" };
setData(data); // React 不会检测到变化

// ✅ 正确做法
setData({
  ...data,
  user: { name: "new name" }
});
```

### 8️⃣ 列表渲染错误

**错误 21-22: 使用索引作为 key**
```typescript
// ❌ 错误示例
list.map((item, index) => {
  return <div key={index}>{item}</div>;
});

// ✅ 正确做法
list.map((item) => {
  return <div key={item.id}>{item}</div>; // 使用唯一标识符
});
```

### 9️⃣ 可访问性错误

**错误 27-28: 可访问性问题**
```typescript
// ❌ 错误示例
<img src="/logo.png" />
<input type="text" placeholder="Enter name" />

// ✅ 正确做法
<img src="/logo.png" alt="Company Logo" />
<label htmlFor="name">Name:</label>
<input type="text" id="name" placeholder="Enter name" />
```

### 🔟 安全相关错误

**错误 17: 危险的 innerHTML 使用**
```typescript
// ❌ 错误示例
const htmlContent = "<script>alert('xss')</script>";
<div dangerouslySetInnerHTML={{ __html: htmlContent }} />

// ✅ 正确做法
import DOMPurify from 'dompurify';

const cleanContent = DOMPurify.sanitize(htmlContent);
<div dangerouslySetInnerHTML={{ __html: cleanContent }} />
```

### 1️⃣1️⃣ 性能相关错误

**错误 23: 内联样式对象**
```typescript
// ❌ 错误示例
<div style={{ color: "red", fontSize: "14px" }}>Text</div>

// ✅ 正确做法
const styles = { color: "red", fontSize: "14px" };
<div style={styles}>Text</div>

// 或使用 CSS 类
<div className="text-red text-14">Text</div>
```

**错误 24: 不必要的箭头函数**
```typescript
// ❌ 错误示例
<button onClick={() => handleUpdate()}>Update</button>

// ✅ 正确做法
<button onClick={handleUpdate}>Update</button>
```

### 1️⃣2️⃣ 表单处理错误

**错误 26: 未防止默认行为**
```typescript
// ❌ 错误示例
<form>
  <input type="text" />
  <button type="submit">Submit</button>
</form>

// ✅ 正确做法
const handleSubmit = (e: React.FormEvent) => {
  e.preventDefault();
  // 处理提交逻辑
};

<form onSubmit={handleSubmit}>
  <input type="text" />
  <button type="submit">Submit</button>
</form>
```

### 1️⃣3️⃣ 工具函数错误

**错误 32-34: 缺少验证和边界检查**
```typescript
// ❌ 错误示例
export function calculateTotal(items) {
  return items.reduce((sum, item) => sum + item.price, 0);
}

export function divide(a, b) {
  return a / b; // 可能除以零
}

export function updateUser(user, updates) {
  Object.assign(user, updates); // 直接修改原对象
  return user;
}

// ✅ 正确做法
export function calculateTotal(items: Array<{ price: number }>): number {
  if (!Array.isArray(items)) {
    throw new Error('Items must be an array');
  }
  return items.reduce((sum, item) => sum + (item.price || 0), 0);
}

export function divide(a: number, b: number): number {
  if (b === 0) {
    throw new Error('Division by zero');
  }
  return a / b;
}

export function updateUser(user: User, updates: Partial<User>): User {
  return { ...user, ...updates }; // 返回新对象
}
```

## 📝 总结

这些错误涵盖了前端开发中的主要问题领域：

1. **类型安全** - 避免使用 `any`，正确使用 TypeScript
2. **Hooks 使用** - 正确的依赖数组、清理函数
3. **内存管理** - 清理定时器、订阅等
4. **状态管理** - 不直接修改状态，使用不可变更新
5. **性能优化** - 避免不必要的重新渲染
6. **可访问性** - 使用语义化标签和正确的 ARIA 属性
7. **安全性** - 防止 XSS 攻击
8. **错误处理** - 适当的错误边界和错误处理
9. **代码质量** - 避免回调地狱，使用 async/await

通过避免这些常见错误，可以编写出更健壮、可维护的前端代码。
